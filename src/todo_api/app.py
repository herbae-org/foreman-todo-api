from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

from todo_api.db import _row_to_todo, get_connection, init_schema


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


class Todo(BaseModel):
    id: int
    title: str
    done: bool
    created_at: datetime


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
    conn.close()
    return _row_to_todo(row)


@app.get("/todos")
def list_todos(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    done: bool | None = Query(default=None),
) -> TodoList:
    conn = get_connection()
    done_val = int(done) if done is not None else None
    rows = conn.execute(
        "SELECT * FROM todos WHERE (? IS NULL OR done = ?) "
        "ORDER BY id DESC LIMIT ? OFFSET ?",
        (done_val, done_val, limit, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM todos WHERE (? IS NULL OR done = ?)",
        (done_val, done_val),
    ).fetchone()[0]
    conn.close()
    return TodoList(items=[_row_to_todo(r) for r in rows], total=total)


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
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return _row_to_todo(row)


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
    conn.close()
    return _row_to_todo(row)


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int) -> Response:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)
