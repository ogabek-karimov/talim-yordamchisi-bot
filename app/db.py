"""Async SQLAlchemy engine / session / Base."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import DATA_DIR, settings


class Base(DeclarativeBase):
    pass


def _normalize_url(url: str) -> tuple[str, dict]:
    """Return an async SQLAlchemy URL + connect_args.

    Accepts the connection strings people actually paste (Neon/Supabase/Render):
    ``postgres://`` / ``postgresql://`` without an async driver, and libpq query
    params (``sslmode``, ``channel_binding``) that ``asyncpg`` does not understand.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    connect_args: dict = {}

    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    elif url.startswith("sqlite://") and "+aiosqlite" not in url:
        return "sqlite+aiosqlite://" + url[len("sqlite://") :], {"check_same_thread": False}

    if url.startswith("sqlite"):
        return url, {"check_same_thread": False}

    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        q = dict(parse_qsl(parts.query))
        sslmode = q.pop("sslmode", None)
        q.pop("channel_binding", None)
        q.pop("options", None)
        if sslmode == "disable":
            connect_args["ssl"] = False
        elif sslmode in ("require", "verify-ca", "verify-full"):
            connect_args["ssl"] = "require"
        else:
            # sslmode absent / prefer / allow: try TLS, fall back to plaintext.
            # Works for managed providers (Neon/Supabase/Render, all TLS) and local PG.
            connect_args["ssl"] = "prefer"
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

    return url, connect_args


DATABASE_URL, _connect_args = _normalize_url(settings.database_url)

if DATABASE_URL.startswith("sqlite"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional session for use in bot handlers / services / scripts."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — commits on success, rolls back on error."""
    async with session_scope() as session:
        yield session


async def init_models() -> None:
    # Import models so they register on Base.metadata before create_all.
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
