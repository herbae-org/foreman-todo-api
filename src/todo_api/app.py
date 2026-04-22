from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI()


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Todo(BaseModel):
    id: int
    title: str
    done: bool
    created_at: datetime


class TodoList(BaseModel):
    items: list[Todo]
    total: int


_todos: list[Todo] = []


def _next_id() -> int:
    return len(_todos) + 1


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/todos", status_code=201)
def create_todo(body: TodoCreate) -> Todo:
    todo = Todo(
        id=_next_id(),
        title=body.title,
        done=False,
        created_at=datetime.now(timezone.utc),
    )
    _todos.append(todo)
    return todo


@app.get("/todos")
def list_todos(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TodoList:
    sorted_todos = sorted(_todos, key=lambda t: t.id, reverse=True)
    page = sorted_todos[offset : offset + limit]
    return TodoList(items=page, total=len(_todos))


@app.get("/todos/{todo_id}")
def get_todo(todo_id: int) -> Todo:
    for todo in _todos:
        if todo.id == todo_id:
            return todo
    raise HTTPException(status_code=404, detail="Not Found")
