from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, EmailStr, Field

from todo_api.auth import (
    JWT_EXPIRY_SECONDS,
    create_token,
    decode_token_from_ws_headers,
    get_current_user,
    hash_password,
    verify_password,
)
from todo_api.events import bus
from todo_api.db import (
    _delete_affected,
    _row_to_tag,
    _row_to_todo,
    close_pool,
    get_db,
    get_pool,
    get_tags_for_todo,
    init_schema,
)
from todo_api.rate_limit import anon_rate_limit, authed_rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await init_schema(conn)
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)


# --- Auth models ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


# --- Todo / Tag models ---

class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class PatchTodo(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, min_length=1, max_length=200)
    done: bool | None = None


class Tag(BaseModel):
    id: int
    name: str


class TagCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=50)


class TagAssign(BaseModel):
    model_config = {"extra": "forbid"}
    tag_ids: list[int]


class TagList(BaseModel):
    items: list[Tag]
    total: int


class Todo(BaseModel):
    id: int
    title: str
    done: bool
    created_at: datetime
    tags: list[Tag] = []


class TodoList(BaseModel):
    items: list[Todo]
    total: int


class TodoStats(BaseModel):
    total: int
    done: int
    pending: int


# --- Auth endpoints ---

@app.post("/auth/register", status_code=201)
async def register(
    body: UserCreate,
    _: str = Depends(anon_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> UserResponse:
    now = datetime.now(timezone.utc)
    hashed = hash_password(body.password)
    try:
        row = await conn.fetchrow(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES (LOWER($1), $2, $3) RETURNING id, email, created_at",
            body.email, hashed, now,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already registered")
    return UserResponse(id=row["id"], email=row["email"], created_at=row["created_at"])


@app.post("/auth/login")
async def login(
    body: LoginRequest,
    _: str = Depends(anon_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> LoginResponse:
    row = await conn.fetchrow(
        "SELECT * FROM users WHERE LOWER(email) = LOWER($1)", body.email,
    )
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(row["id"])
    return LoginResponse(
        access_token=token, token_type="bearer", expires_in=JWT_EXPIRY_SECONDS,
    )


@app.get("/auth/me")
async def get_me(
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> UserResponse:
    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return UserResponse(
        id=row["id"],
        email=row["email"],
        created_at=row["created_at"],
    )


# --- Health ---

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# --- Todo endpoints ---

@app.post("/todos", status_code=201)
async def create_todo(
    body: TodoCreate,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Todo:
    now = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        "INSERT INTO todos (user_id, title, done, created_at) "
        "VALUES ($1, $2, FALSE, $3) RETURNING *",
        user_id, body.title, now,
    )
    tags = await get_tags_for_todo(conn, row["id"])
    todo = _row_to_todo(row, tags)
    await bus.publish(user_id, {"type": "created", "todo": todo.model_dump(mode="json")})
    return todo


@app.get("/todos")
async def list_todos(
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    done: bool | None = Query(default=None),
    tag_ids: list[int] | None = Query(default=None),
) -> TodoList:
    has_tag_filter = bool(tag_ids)
    tag_list = tag_ids if tag_ids else []

    params: list[object] = [user_id]
    idx = 2

    if done is not None:
        done_clause = f"AND t.done = ${idx}"
        params.append(done)
        idx += 1
    else:
        done_clause = ""

    if has_tag_filter:
        placeholders = ", ".join(f"${idx + i}" for i in range(len(tag_list)))
        tag_clause = f"AND tt.tag_id IN ({placeholders})"
        params.extend(tag_list)
        idx += len(tag_list)
    else:
        tag_clause = ""

    params.extend([limit, offset])
    limit_idx = idx
    offset_idx = idx + 1

    rows = await conn.fetch(
        "SELECT DISTINCT t.* FROM todos t "
        "LEFT JOIN todo_tags tt ON tt.todo_id = t.id "
        f"WHERE t.user_id = $1 {done_clause} {tag_clause} "
        f"ORDER BY t.id DESC LIMIT ${limit_idx} OFFSET ${offset_idx}",
        *params,
    )

    count_params = params[:-2]
    count_row = await conn.fetchrow(
        "SELECT COUNT(DISTINCT t.id) AS cnt FROM todos t "
        "LEFT JOIN todo_tags tt ON tt.todo_id = t.id "
        f"WHERE t.user_id = $1 {done_clause} {tag_clause}",
        *count_params,
    )
    total = count_row["cnt"]

    items = []
    for r in rows:
        tags = await get_tags_for_todo(conn, r["id"])
        items.append(_row_to_todo(r, tags))
    return TodoList(items=items, total=total)


@app.get("/todos/stats")
async def get_stats(
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> TodoStats:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS total, "
        "COUNT(*) FILTER (WHERE done) AS done "
        "FROM todos WHERE user_id = $1",
        user_id,
    )
    total = row["total"]
    done_count = row["done"]
    return TodoStats(total=total, done=done_count, pending=total - done_count)


@app.get("/todos/{todo_id}")
async def get_todo(
    todo_id: int,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Todo:
    row = await conn.fetchrow(
        "SELECT * FROM todos WHERE id = $1 AND user_id = $2", todo_id, user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not Found")
    tags = await get_tags_for_todo(conn, row["id"])
    return _row_to_todo(row, tags)


@app.patch("/todos/{todo_id}")
async def patch_todo(
    todo_id: int,
    body: PatchTodo,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Todo:
    affected = await _delete_affected(
        conn,
        "UPDATE todos SET title = COALESCE($1, title), done = COALESCE($2, done) "
        "WHERE id = $3 AND user_id = $4",
        body.title, body.done, todo_id, user_id,
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    row = await conn.fetchrow(
        "SELECT * FROM todos WHERE id = $1", todo_id,
    )
    tags = await get_tags_for_todo(conn, row["id"])
    todo = _row_to_todo(row, tags)
    await bus.publish(user_id, {"type": "updated", "todo": todo.model_dump(mode="json")})
    return todo


@app.delete("/todos/{todo_id}", status_code=204)
async def delete_todo(
    todo_id: int,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Response:
    row = await conn.fetchrow(
        "SELECT * FROM todos WHERE id = $1 AND user_id = $2", todo_id, user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not Found")
    tags = await get_tags_for_todo(conn, row["id"])
    pre_delete_todo = _row_to_todo(row, tags)
    await conn.execute("DELETE FROM todos WHERE id = $1", todo_id)
    await bus.publish(user_id, {"type": "deleted", "todo": pre_delete_todo.model_dump(mode="json")})
    return Response(status_code=204)


# --- Tag endpoints ---

@app.post("/tags", status_code=201)
async def create_tag(
    body: TagCreate,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Tag:
    try:
        row = await conn.fetchrow(
            "INSERT INTO tags (user_id, name) VALUES ($1, $2) RETURNING id, name",
            user_id, body.name,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Tag already exists")
    return _row_to_tag(row)


@app.get("/tags")
async def list_tags(
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> TagList:
    rows = await conn.fetch(
        "SELECT * FROM tags WHERE user_id = $1 ORDER BY id DESC", user_id,
    )
    return TagList(items=[_row_to_tag(r) for r in rows], total=len(rows))


@app.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Response:
    affected = await _delete_affected(
        conn,
        "DELETE FROM tags WHERE id = $1 AND user_id = $2", tag_id, user_id,
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)


# --- Todo-Tag endpoints ---

@app.post("/todos/{todo_id}/tags")
async def assign_tags(
    todo_id: int,
    body: TagAssign,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Todo:
    row = await conn.fetchrow(
        "SELECT * FROM todos WHERE id = $1 AND user_id = $2", todo_id, user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not Found")
    for tid in body.tag_ids:
        exists = await conn.fetchrow(
            "SELECT id FROM tags WHERE id = $1 AND user_id = $2", tid, user_id,
        )
        if exists is None:
            raise HTTPException(
                status_code=400, detail=f"Unknown tag_id: {tid}"
            )
    for tid in body.tag_ids:
        await conn.execute(
            "INSERT INTO todo_tags (todo_id, tag_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            todo_id, tid,
        )
    tags = await get_tags_for_todo(conn, row["id"])
    todo = _row_to_todo(row, tags)
    await bus.publish(user_id, {"type": "updated", "todo": todo.model_dump(mode="json")})
    return todo


@app.delete("/todos/{todo_id}/tags/{tag_id}", status_code=204)
async def remove_tag(
    todo_id: int,
    tag_id: int,
    user_id: int = Depends(authed_rate_limit),
    conn: asyncpg.Connection = Depends(get_db),
) -> Response:
    todo_row = await conn.fetchrow(
        "SELECT id FROM todos WHERE id = $1 AND user_id = $2", todo_id, user_id,
    )
    if todo_row is None:
        raise HTTPException(status_code=404, detail="Not Found")
    affected = await _delete_affected(
        conn,
        "DELETE FROM todo_tags WHERE todo_id = $1 AND tag_id = $2",
        todo_id, tag_id,
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    row = await conn.fetchrow(
        "SELECT * FROM todos WHERE id = $1", todo_id,
    )
    tags = await get_tags_for_todo(conn, todo_id)
    todo = _row_to_todo(row, tags)
    await bus.publish(user_id, {"type": "updated", "todo": todo.model_dump(mode="json")})
    return Response(status_code=204)


# --- WebSocket ---

@app.websocket("/ws/todos")
async def todos_stream(ws: WebSocket) -> None:
    user_id = decode_token_from_ws_headers(ws)
    await ws.accept()
    await ws.send_json({"type": "hello", "user_id": user_id})
    queue = bus.subscribe(user_id)
    try:
        while True:
            event = await queue.get()
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception:
        await ws.close(code=1011, reason="internal error")
    finally:
        bus.unsubscribe(user_id, queue)
