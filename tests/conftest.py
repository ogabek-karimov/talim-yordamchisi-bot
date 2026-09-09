"""Test configuration. Env is set BEFORE importing the app."""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="talim-test-")
os.environ.update(
    {
        "BOT_TOKEN": "",  # -> get_bot() returns None, no network
        "OWNER_ID": "500000",
        "USE_POLLING": "0",
        "WEBHOOK_BASE": "",
        "WEBAPP_URL": "https://example.test/app",
        "SESSION_SECRET": "test-session-secret",
        "WEBHOOK_SECRET": "test-webhook-secret",
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
        "AI_PROVIDER": "",
        "AI_FALLBACK": "",
        "OPENAI_API_KEY": "",
        "GEMINI_API_KEY": "",
        "OLLAMA_BASE_URL": "",
    }
)

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.db import Base, engine, session_scope  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, Status, User  # noqa: E402
from app.security import issue_session  # noqa: E402
from app.services import settings_store, users as users_svc  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with session_scope() as s:
        await settings_store.ensure_defaults(s)
        await users_svc.ensure_owner(s)
    yield


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest_asyncio.fixture
async def make_user():
    async def _make(
        tg_id: int,
        *,
        role: str = Role.USER,
        status: str = Status.APPROVED,
        language: str = "uz",
    ) -> User:
        async with session_scope() as s:
            user, _ = await users_svc.get_or_create(s, tg_id, first_name=f"U{tg_id}", language=language)
            user.role = role
            user.status = status
            await s.flush()
        return user

    return _make


def auth_header(tg_id: int) -> dict:
    return {"Authorization": f"Bearer {issue_session(tg_id)}"}
