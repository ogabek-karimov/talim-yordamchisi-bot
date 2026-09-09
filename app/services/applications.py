"""Access applications ("ariza") submitted by prospective users."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, AppStatus, utcnow
from app.services import audit, users


async def pending_for(session: AsyncSession, tg_id: int) -> Application | None:
    return (
        await session.execute(
            select(Application)
            .where(Application.tg_id == tg_id, Application.status == AppStatus.PENDING)
            .order_by(Application.id.desc())
        )
    ).scalars().first()


async def create(
    session: AsyncSession,
    *,
    tg_id: int,
    username: str | None,
    full_name: str,
    phone: str,
    language: str,
) -> Application:
    app = Application(
        tg_id=tg_id,
        username=username,
        full_name=full_name.strip(),
        phone=phone.strip(),
        language=language,
        status=AppStatus.PENDING,
    )
    session.add(app)
    await session.flush()
    return app


async def list_pending(session: AsyncSession, *, limit: int = 100) -> list[Application]:
    rows = await session.execute(
        select(Application)
        .where(Application.status == AppStatus.PENDING)
        .order_by(Application.id.asc())
        .limit(limit)
    )
    return list(rows.scalars().all())


async def get(session: AsyncSession, app_id: int) -> Application | None:
    return await session.get(Application, app_id)


async def approve(
    session: AsyncSession, app_id: int, *, by: int | None
) -> Application | None:
    app = await session.get(Application, app_id)
    if app is None or app.status != AppStatus.PENDING:
        return None
    app.status = AppStatus.APPROVED
    app.decided_by = by
    app.decided_at = utcnow()
    await users.approve(
        session,
        app.tg_id,
        by=by,
        username=app.username,
        name=app.full_name,
        phone=app.phone,
        language=app.language,
    )
    await session.flush()
    await audit.record(
        session, actor_tg_id=by, action="application.approve", target=str(app.tg_id)
    )
    return app


async def reject(
    session: AsyncSession, app_id: int, *, by: int | None, reason: str | None = None
) -> Application | None:
    app = await session.get(Application, app_id)
    if app is None or app.status != AppStatus.PENDING:
        return None
    app.status = AppStatus.REJECTED
    app.decided_by = by
    app.decided_at = utcnow()
    app.note = (reason or "").strip() or None
    await session.flush()
    await audit.record(
        session, actor_tg_id=by, action="application.reject", target=str(app.tg_id)
    )
    return app
