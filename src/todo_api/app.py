import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

from todo_api.db import _row_to_tag, _row_to_todo, get_connection, get_tags_for_todo, init_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_connection()
    init_schema(conn)
    conn.close()
    yield


app = FastAPI(lifespan=lifespan)


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/todos", status_code=201)
def create_todo(body: TodoCreate) -> Todo:
    now = datetime.now(timezone.utc)
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO todos (title, done, created_at) VALUES (?, 0, ?)",
        (body.title, now.isoformat()),
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
        f"WHERE (? IS NULL OR t.done = ?) "
        f"  AND (? = 0 OR tt.tag_id IN ({placeholders})) "
        "ORDER BY t.id DESC LIMIT ? OFFSET ?",
        [done_val, done_val, has_tag_filter] + tag_params + [limit, offset],
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(DISTINCT t.id) FROM todos t "
        "LEFT JOIN todo_tags tt ON tt.todo_id = t.id "
        f"WHERE (? IS NULL OR t.done = ?) "
        f"  AND (? = 0 OR tt.tag_id IN ({placeholders}))",
        [done_val, done_val, has_tag_filter] + tag_params,
    ).fetchone()[0]
    items = [_row_to_todo(r, conn) for r in rows]
    conn.close()
    return TodoList(items=items, total=total)


@app.get("/todos/stats")
def get_stats() -> TodoStats:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(done) AS done FROM todos"
    ).fetchone()
    conn.close()
    total = row["total"]
    done_count = row["done"] or 0
    return TodoStats(total=total, done=done_count, pending=total - done_count)


@app.get("/todos/{todo_id}")
def get_todo(todo_id: int) -> Todo:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM todos WHERE id = ?", (todo_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Not Found")
    todo = _row_to_todo(row, conn)
    conn.close()
    return todo


@app.patch("/todos/{todo_id}")
def patch_todo(todo_id: int, body: PatchTodo) -> Todo:
    conn = get_connection()
    done_val = int(body.done) if body.done is not None else None
    cursor = conn.execute(
        "UPDATE todos SET title = COALESCE(?, title), done = COALESCE(?, done) "
        "WHERE id = ?",
        (body.title, done_val, todo_id),
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
def delete_todo(todo_id: int) -> Response:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)


@app.post("/tags", status_code=201)
def create_tag(body: TagCreate) -> Tag:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO tags (name) VALUES (?)", (body.name,)
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
def list_tags() -> TagList:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tags ORDER BY id DESC").fetchall()
    conn.close()
    return TagList(items=[_row_to_tag(r) for r in rows], total=len(rows))


@app.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int) -> Response:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)


@app.post("/todos/{todo_id}/tags")
def assign_tags(todo_id: int, body: TagAssign) -> Todo:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM todos WHERE id = ?", (todo_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Not Found")
    for tid in body.tag_ids:
        exists = conn.execute(
            "SELECT id FROM tags WHERE id = ?", (tid,)
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
def remove_tag(todo_id: int, tag_id: int) -> Response:
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM todo_tags WHERE todo_id = ? AND tag_id = ?",
        (todo_id, tag_id),
    )
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)
