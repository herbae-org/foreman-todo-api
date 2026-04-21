from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI()


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Todo(BaseModel):
    id: int
    title: str
    done: bool
    created_at: datetime


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
