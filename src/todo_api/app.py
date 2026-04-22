import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, Field

from todo_api.auth import (
    JWT_EXPIRY_SECONDS,
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from todo_api.db import _row_to_tag, _row_to_todo, get_connection, get_tags_for_todo, init_schema
from todo_api.rate_limit import anon_rate_limit, authed_rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_connection()
    init_schema(conn)
    conn.close()
    yield


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
def register(body: UserCreate, _: str = Depends(anon_rate_limit)) -> UserResponse:
    conn = get_connection()
    now = datetime.now(timezone.utc)
    hashed = hash_password(body.password)
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (body.email, hashed, now.isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Email already registered")
    user_id = cursor.lastrowid
    conn.close()
    return UserResponse(id=user_id, email=body.email, created_at=now)


@app.post("/auth/login")
def login(body: LoginRequest, _: str = Depends(anon_rate_limit)) -> LoginResponse:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (body.email,)
    ).fetchone()
    conn.close()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(row["id"])
    return LoginResponse(
        access_token=token, token_type="bearer", expires_in=JWT_EXPIRY_SECONDS,
    )


@app.get("/auth/me")
def get_me(user_id: int = Depends(authed_rate_limit)) -> UserResponse:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return UserResponse(
        id=row["id"],
        email=row["email"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


# --- Health ---

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --- Todo endpoints ---

@app.post("/todos", status_code=201)
def create_todo(body: TodoCreate, user_id: int = Depends(authed_rate_limit)) -> Todo:
    now = datetime.now(timezone.utc)
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO todos (user_id, title, done, created_at) VALUES (?, ?, 0, ?)",
        (user_id, body.title, now.isoformat()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM todos WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    todo = _row_to_todo(row, conn)
    conn.close()
    return todo


@app.get("/todos")
def list_todos(
    user_id: int = Depends(authed_rate_limit),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    done: bool | None = Query(default=None),
    tag_ids: list[int] | None = Query(default=None),
) -> TodoList:
    conn = get_connection()
    done_val = int(done) if done is not None else None
    has_tag_filter = int(bool(tag_ids))
    placeholders = ",".join("?" * len(tag_ids)) if tag_ids else "NULL"
    tag_params = list(tag_ids) if tag_ids else []

    rows = conn.execute(
        "SELECT DISTINCT t.* FROM todos t "
        "LEFT JOIN todo_tags tt ON tt.todo_id = t.id "
        f"WHERE t.user_id = ? "
        f"  AND (? IS NULL OR t.done = ?) "
        f"  AND (? = 0 OR tt.tag_id IN ({placeholders})) "
        "ORDER BY t.id DESC LIMIT ? OFFSET ?",
        [user_id, done_val, done_val, has_tag_filter] + tag_params + [limit, offset],
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(DISTINCT t.id) FROM todos t "
        "LEFT JOIN todo_tags tt ON tt.todo_id = t.id "
        f"WHERE t.user_id = ? "
        f"  AND (? IS NULL OR t.done = ?) "
        f"  AND (? = 0 OR tt.tag_id IN ({placeholders}))",
        [user_id, done_val, done_val, has_tag_filter] + tag_params,
    ).fetchone()[0]
    items = [_row_to_todo(r, conn) for r in rows]
    conn.close()
    return TodoList(items=items, total=total)


@app.get("/todos/stats")
def get_stats(user_id: int = Depends(authed_rate_limit)) -> TodoStats:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(done) AS done FROM todos WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    total = row["total"]
    done_count = row["done"] or 0
    return TodoStats(total=total, done=done_count, pending=total - done_count)


@app.get("/todos/{todo_id}")
def get_todo(todo_id: int, user_id: int = Depends(authed_rate_limit)) -> Todo:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Not Found")
    todo = _row_to_todo(row, conn)
    conn.close()
    return todo


@app.patch("/todos/{todo_id}")
def patch_todo(
    todo_id: int, body: PatchTodo, user_id: int = Depends(authed_rate_limit)
) -> Todo:
    conn = get_connection()
    done_val = int(body.done) if body.done is not None else None
    cursor = conn.execute(
        "UPDATE todos SET title = COALESCE(?, title), done = COALESCE(?, done) "
        "WHERE id = ? AND user_id = ?",
        (body.title, done_val, todo_id, user_id),
    )
    conn.commit()
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Not Found")
    row = conn.execute(
        "SELECT * FROM todos WHERE id = ?", (todo_id,)
    ).fetchone()
    todo = _row_to_todo(row, conn)
    conn.close()
    return todo


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int, user_id: int = Depends(authed_rate_limit)) -> Response:
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)
    )
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)


# --- Tag endpoints ---

@app.post("/tags", status_code=201)
def create_tag(body: TagCreate, user_id: int = Depends(authed_rate_limit)) -> Tag:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO tags (user_id, name) VALUES (?, ?)", (user_id, body.name)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Tag already exists")
    row = conn.execute(
        "SELECT * FROM tags WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    conn.close()
    return _row_to_tag(row)


@app.get("/tags")
def list_tags(user_id: int = Depends(authed_rate_limit)) -> TagList:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tags WHERE user_id = ? ORDER BY id DESC", (user_id,)
    ).fetchall()
    conn.close()
    return TagList(items=[_row_to_tag(r) for r in rows], total=len(rows))


@app.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, user_id: int = Depends(authed_rate_limit)) -> Response:
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM tags WHERE id = ? AND user_id = ?", (tag_id, user_id)
    )
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)


# --- Todo-Tag endpoints ---

@app.post("/todos/{todo_id}/tags")
def assign_tags(
    todo_id: int, body: TagAssign, user_id: int = Depends(authed_rate_limit)
) -> Todo:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Not Found")
    for tid in body.tag_ids:
        exists = conn.execute(
            "SELECT id FROM tags WHERE id = ? AND user_id = ?", (tid, user_id)
        ).fetchone()
        if exists is None:
            conn.close()
            raise HTTPException(
                status_code=400, detail=f"Unknown tag_id: {tid}"
            )
    for tid in body.tag_ids:
        conn.execute(
            "INSERT OR IGNORE INTO todo_tags (todo_id, tag_id) VALUES (?, ?)",
            (todo_id, tid),
        )
    conn.commit()
    todo = _row_to_todo(row, conn)
    conn.close()
    return todo


@app.delete("/todos/{todo_id}/tags/{tag_id}", status_code=204)
def remove_tag(
    todo_id: int, tag_id: int, user_id: int = Depends(authed_rate_limit)
) -> Response:
    conn = get_connection()
    todo_row = conn.execute(
        "SELECT id FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)
    ).fetchone()
    if todo_row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Not Found")
    cursor = conn.execute(
        "DELETE FROM todo_tags WHERE todo_id = ? AND tag_id = ?",
        (todo_id, tag_id),
    )
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)
