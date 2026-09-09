"""User lifecycle: creation, language, approval, roles, ownership transfer."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import normalize_lang
from app.models import Application, AppStatus, Attempt, Role, Status, User, utcnow
from app.services import audit


async def get_by_tg(session: AsyncSession, tg_id: int) -> User | None:
    return (
        await session.execute(select(User).where(User.tg_id == tg_id))
    ).scalar_one_or_none()


async def get_or_create(
    session: AsyncSession,
    tg_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language: str | None = None,
) -> tuple[User, bool]:
    user = await get_by_tg(session, tg_id)
    created = False
    if user is None:
        user = User(
            tg_id=tg_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language=normalize_lang(language) if language else settings.default_lang,
            role=Role.USER,
            status=Status.PENDING,
        )
        session.add(user)
        created = True
    else:
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name

    # The configured owner is always owner+approved.
    if settings.owner_id and tg_id == settings.owner_id:
        user.role = Role.OWNER
        user.status = Status.APPROVED

    user.last_seen_at = utcnow()
    await session.flush()
    return user, created


async def ensure_owner(session: AsyncSession) -> User | None:
    if not settings.owner_id:
        return None
    user, _ = await get_or_create(session, settings.owner_id, first_name="Owner")
    user.role = Role.OWNER
    user.status = Status.APPROVED
    await session.flush()
    return user


async def set_language(session: AsyncSession, user: User, lang: str) -> None:
    user.language = normalize_lang(lang)
    await session.flush()


async def approve(
    session: AsyncSession,
    tg_id: int,
    *,
    by: int | None,
    username: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    language: str | None = None,
) -> User:
    user, _ = await get_or_create(session, tg_id, username=username, language=language)
    if name and not (user.first_name or user.last_name):
        first, _, last = name.strip().partition(" ")
        user.first_name = first or user.first_name
        user.last_name = last or user.last_name
    if phone:
        user.phone = phone
    if user.role not in Role.STAFF:
        user.role = Role.USER
    user.status = Status.APPROVED
    user.approved_by = by
    user.approved_at = utcnow()
    await session.flush()
    await audit.record(session, actor_tg_id=by, action="user.approve", target=str(tg_id))
    return user


async def add_manual(
    session: AsyncSession, tg_id: int, *, by: int | None, name: str | None = None
) -> tuple[User, bool]:
    existing = await get_by_tg(session, tg_id)
    already = existing is not None and existing.status == Status.APPROVED
    user = await approve(session, tg_id, by=by, name=name)
    return user, already


async def set_status(
    session: AsyncSession, tg_id: int, status: str, *, by: int | None
) -> User | None:
    user = await get_by_tg(session, tg_id)
    if user is None:
        return None
    if user.role == Role.OWNER:
        return user  # never touch the owner
    user.status = status
    await session.flush()
    await audit.record(
        session, actor_tg_id=by, action=f"user.{status}", target=str(tg_id)
    )
    return user


async def block(session: AsyncSession, tg_id: int, *, by: int | None) -> User | None:
    return await set_status(session, tg_id, Status.BLOCKED, by=by)


async def unblock(session: AsyncSession, tg_id: int, *, by: int | None) -> User | None:
    return await set_status(session, tg_id, Status.APPROVED, by=by)


async def remove(session: AsyncSession, tg_id: int, *, by: int | None) -> User | None:
    """Revoke access (back to pending) without deleting history."""
    user = await get_by_tg(session, tg_id)
    if user is None or user.role == Role.OWNER:
        return user
    user.status = Status.PENDING
    user.role = Role.USER
    await session.flush()
    await audit.record(session, actor_tg_id=by, action="user.remove", target=str(tg_id))
    return user


async def make_admin(session: AsyncSession, tg_id: int, *, by: int | None) -> User:
    user = await approve(session, tg_id, by=by)
    user.role = Role.ADMIN
    await session.flush()
    await audit.record(session, actor_tg_id=by, action="admin.add", target=str(tg_id))
    return user


async def remove_admin(session: AsyncSession, tg_id: int, *, by: int | None) -> User | None:
    user = await get_by_tg(session, tg_id)
    if user is None or user.role != Role.ADMIN:
        return user
    user.role = Role.USER
    await session.flush()
    await audit.record(session, actor_tg_id=by, action="admin.remove", target=str(tg_id))
    return user


async def transfer_ownership(
    session: AsyncSession, target_tg_id: int, *, by: int | None
) -> User:
    """Promote ``target`` to owner and demote the current owner to admin."""
    target = await get_by_tg(session, target_tg_id)
    if target is None or target.role != Role.ADMIN:
        raise ValueError("target must be an existing admin")

    current = (
        await session.execute(select(User).where(User.role == Role.OWNER))
    ).scalars().all()
    for owner in current:
        if owner.tg_id != target_tg_id:
            owner.role = Role.ADMIN

    target.role = Role.OWNER
    target.status = Status.APPROVED
    await session.flush()
    await audit.record(
        session,
        actor_tg_id=by,
        action="ownership.transfer",
        target=str(target_tg_id),
        meta={"from": [o.tg_id for o in current]},
    )
    return target


async def list_users(
    session: AsyncSession,
    *,
    roles: list[str] | None = None,
    statuses: list[str] | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[User]:
    stmt = select(User)
    if roles:
        stmt = stmt.where(User.role.in_(roles))
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))
    if query:
        like = f"%{query}%"
        conds = [User.username.ilike(like), User.first_name.ilike(like), User.last_name.ilike(like)]
        if query.lstrip("-").isdigit():
            conds.append(User.tg_id == int(query))
        stmt = stmt.where(or_(*conds))
    stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


async def staff_ids(session: AsyncSession) -> list[int]:
    rows = await session.execute(select(User.tg_id).where(User.role.in_(Role.STAFF)))
    ids = set(rows.scalars().all())
    if settings.owner_id:
        ids.add(settings.owner_id)
    return sorted(ids)


async def staff_users(session: AsyncSession) -> list[User]:
    rows = await session.execute(
        select(User).where(User.role.in_(Role.STAFF)).order_by(User.role)
    )
    return list(rows.scalars().all())


async def approved_ids(session: AsyncSession) -> list[int]:
    rows = await session.execute(
        select(User.tg_id).where(User.status == Status.APPROVED)
    )
    return list(rows.scalars().all())


async def counts(session: AsyncSession) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    total = (await session.execute(select(func.count(User.id)))).scalar_one()
    approved = (
        await session.execute(
            select(func.count(User.id)).where(User.status == Status.APPROVED)
        )
    ).scalar_one()
    pending_apps = (
        await session.execute(
            select(func.count(Application.id)).where(
                Application.status == AppStatus.PENDING
            )
        )
    ).scalar_one()
    active_subs = (
        await session.execute(
            select(func.count(User.id)).where(User.subscription_until > now)
        )
    ).scalar_one()
    attempts = (await session.execute(select(func.count(Attempt.id)))).scalar_one()
    return {
        "users": int(total),
        "approved": int(approved),
        "pending": int(pending_apps),
        "active_subs": int(active_subs),
        "attempts": int(attempts),
    }
