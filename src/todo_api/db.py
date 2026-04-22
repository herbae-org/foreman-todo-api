from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todo_api.app import Tag, Todo

DB_PATH: Path = Path(os.environ.get("TODO_DB_PATH", ":memory:"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS todos ("
        "    id         INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    title      TEXT    NOT NULL,"
        "    done       INTEGER NOT NULL DEFAULT 0,"
        "    created_at TEXT    NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tags ("
        "    id   INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    name TEXT    NOT NULL UNIQUE COLLATE NOCASE"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS todo_tags ("
        "    todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,"
        "    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,"
        "    PRIMARY KEY (todo_id, tag_id)"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_todo_tags_tag ON todo_tags(tag_id)"
    )
    conn.commit()


def _row_to_tag(row: sqlite3.Row) -> Tag:
    from todo_api.app import Tag

    return Tag(id=row["id"], name=row["name"])


def get_tags_for_todo(conn: sqlite3.Connection, todo_id: int) -> list[Tag]:
    rows = conn.execute(
        "SELECT t.id, t.name FROM tags t "
        "JOIN todo_tags tt ON tt.tag_id = t.id "
        "WHERE tt.todo_id = ? ORDER BY t.id",
        (todo_id,),
    ).fetchall()
    return [_row_to_tag(r) for r in rows]


def _row_to_todo(row: sqlite3.Row, conn: sqlite3.Connection) -> Todo:
    from todo_api.app import Todo

    return Todo(
        id=row["id"],
        title=row["title"],
        done=bool(row["done"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        tags=get_tags_for_todo(conn, row["id"]),
    )
