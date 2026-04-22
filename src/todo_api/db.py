from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from todo_api.app import Tag, Todo

DB_PATH: Path = Path(os.environ.get("TODO_DB_PATH", ":memory:"))

IntegrityError = sqlite3.IntegrityError


async def get_connection() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_schema(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "    id            INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,"
        "    password_hash TEXT    NOT NULL,"
        "    created_at    TEXT    NOT NULL"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS todos ("
        "    id         INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "    title      TEXT    NOT NULL,"
        "    done       INTEGER NOT NULL DEFAULT 0,"
        "    created_at TEXT    NOT NULL"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS tags ("
        "    id      INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "    name    TEXT    NOT NULL COLLATE NOCASE,"
        "    UNIQUE(user_id, name) ON CONFLICT ABORT"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS todo_tags ("
        "    todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,"
        "    tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,"
        "    PRIMARY KEY (todo_id, tag_id)"
        ")"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_todo_tags_tag ON todo_tags(tag_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tags_user ON tags(user_id)"
    )
    await conn.commit()


def _row_to_tag(row: aiosqlite.Row) -> Tag:
    from todo_api.app import Tag

    return Tag(id=row["id"], name=row["name"])


async def get_tags_for_todo(conn: aiosqlite.Connection, todo_id: int) -> list[Tag]:
    cursor = await conn.execute(
        "SELECT t.id, t.name FROM tags t "
        "JOIN todo_tags tt ON tt.tag_id = t.id "
        "WHERE tt.todo_id = ? ORDER BY t.id",
        (todo_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_tag(r) for r in rows]


def _row_to_todo(row: aiosqlite.Row, tags: list[Tag] | None = None) -> Todo:
    from todo_api.app import Todo

    return Todo(
        id=row["id"],
        title=row["title"],
        done=bool(row["done"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        tags=tags if tags is not None else [],
    )
