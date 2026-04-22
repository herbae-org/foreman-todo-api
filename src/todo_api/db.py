from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todo_api.app import Todo

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
    conn.commit()


def _row_to_todo(row: sqlite3.Row) -> Todo:
    from todo_api.app import Todo

    return Todo(
        id=row["id"],
        title=row["title"],
        done=bool(row["done"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
