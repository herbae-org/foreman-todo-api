import uuid

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from todo_api import db as db_module
from todo_api import rate_limit
from todo_api.events import bus
from todo_api.app import app


@pytest_asyncio.fixture(autouse=True)
async def isolated_state():
    db_module.terminate_all_pools()

    conn = await asyncpg.connect(db_module.DATABASE_URL)
    try:
        has_tables = await conn.fetchval(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.tables "
            "  WHERE table_schema = 'public' AND table_name = 'users'"
            ")"
        )
        if has_tables:
            await conn.execute(
                "TRUNCATE TABLE todo_tags, tags, todos, users "
                "RESTART IDENTITY CASCADE"
            )
        await db_module.init_schema(conn)
    finally:
        await conn.close()

    rate_limit.reset_buckets()
    bus.reset()


@pytest.fixture
def auth_headers():
    client = TestClient(app)
    email = f"test-user-{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "testpass123"})
    resp = client.post("/auth/login", json={"email": email, "password": "testpass123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
