"""Append-only audit log for privileged actions."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record(
    session: AsyncSession,
    *,
    actor_tg_id: int | None,
    action: str,
    target: str | None = None,
    meta: dict | None = None,
) -> None:
    session.add(
        AuditLog(actor_tg_id=actor_tg_id, action=action, target=target, meta=meta or {})
    )
    await session.flush()


async def recent(session: AsyncSession, limit: int = 50) -> list[AuditLog]:
    rows = await session.execute(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    )
    return list(rows.scalars().all())
