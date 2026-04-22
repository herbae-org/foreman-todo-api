from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from todo_api.app import Tag, Todo

_TESTING = "PYTEST_CURRENT_TEST" in os.environ

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/test" if _TESTING else "",
)

if not DATABASE_URL and not _TESTING:
    raise RuntimeError("DATABASE_URL environment variable is required")

_pools: dict[int, asyncpg.Pool] = {}


async def get_pool() -> asyncpg.Pool:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    pool = _pools.get(loop_id)
    if pool is None or pool._closed:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        _pools[loop_id] = pool
    return pool


async def close_pool() -> None:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    pool = _pools.pop(loop_id, None)
    if pool is not None:
        await pool.close()


def terminate_all_pools() -> None:
    for pool in list(_pools.values()):
        if not pool._closed:
            try:
                pool.terminate()
            except Exception:
                pass
    _pools.clear()


async def init_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "    id            BIGSERIAL PRIMARY KEY,"
        "    email         TEXT NOT NULL UNIQUE,"
        "    password_hash TEXT NOT NULL,"
        "    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS todos ("
        "    id         BIGSERIAL PRIMARY KEY,"
        "    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "    title      TEXT NOT NULL,"
        "    done       BOOLEAN NOT NULL DEFAULT FALSE,"
        "    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS tags ("
        "    id      BIGSERIAL PRIMARY KEY,"
        "    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "    name    TEXT NOT NULL"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS todo_tags ("
        "    todo_id BIGINT NOT NULL REFERENCES todos(id) ON DELETE CASCADE,"
        "    tag_id  BIGINT NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,"
        "    PRIMARY KEY (todo_id, tag_id)"
        ")"
    )
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_user_lower_name "
        "ON tags (user_id, LOWER(name))"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tags_user ON tags(user_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_todo_tags_tag ON todo_tags(tag_id)"
    )


async def get_db() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


def _row_to_tag(row: asyncpg.Record) -> Tag:
    from todo_api.app import Tag

    return Tag(id=row["id"], name=row["name"])


async def get_tags_for_todo(conn: asyncpg.Connection, todo_id: int) -> list[Tag]:
    rows = await conn.fetch(
        "SELECT t.id, t.name FROM tags t "
        "JOIN todo_tags tt ON tt.tag_id = t.id "
        "WHERE tt.todo_id = $1 ORDER BY t.id",
        todo_id,
    )
    return [_row_to_tag(r) for r in rows]


def _row_to_todo(row: asyncpg.Record, tags: list[Tag] | None = None) -> Todo:
    from todo_api.app import Todo

    return Todo(
        id=row["id"],
        title=row["title"],
        done=row["done"],
        created_at=row["created_at"],
        tags=tags if tags is not None else [],
    )


async def _delete_affected(conn: asyncpg.Connection, sql: str, *args: object) -> int:
    return int((await conn.execute(sql, *args)).split()[-1])
