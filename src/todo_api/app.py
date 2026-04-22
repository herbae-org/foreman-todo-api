from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

app = FastAPI()


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
    done: bool | None = Query(default=None),
) -> TodoList:
    if done is not None:
        filtered = [t for t in _todos if t.done is done]
    else:
        filtered = list(_todos)
    sorted_todos = sorted(filtered, key=lambda t: t.id, reverse=True)
    page = sorted_todos[offset : offset + limit]
    return TodoList(items=page, total=len(filtered))


@app.get("/todos/stats")
def get_stats() -> TodoStats:
    done_count = sum(1 for t in _todos if t.done)
    return TodoStats(total=len(_todos), done=done_count, pending=len(_todos) - done_count)


@app.get("/todos/{todo_id}")
def get_todo(todo_id: int) -> Todo:
    for todo in _todos:
        if todo.id == todo_id:
            return todo
    raise HTTPException(status_code=404, detail="Not Found")


@app.patch("/todos/{todo_id}")
def patch_todo(todo_id: int, body: PatchTodo) -> Todo:
    for i, todo in enumerate(_todos):
        if todo.id == todo_id:
            updates = body.model_dump(exclude_none=True)
            _todos[i] = todo.model_copy(update=updates)
            return _todos[i]
    raise HTTPException(status_code=404, detail="Not Found")


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int) -> Response:
    for i, todo in enumerate(_todos):
        if todo.id == todo_id:
            _todos.pop(i)
            return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Not Found")
