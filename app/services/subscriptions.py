"""Subscription gate + Telegram Stars payment bookkeeping."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, User, utcnow
from app.services import audit, settings_store


async def is_enabled(session: AsyncSession) -> bool:
    return await settings_store.subscription_enabled(session)


async def set_enabled(session: AsyncSession, value: bool, *, by: int | None) -> bool:
    await settings_store.set(session, "subscription_enabled", bool(value))
    await audit.record(
        session,
        actor_tg_id=by,
        action="subscription.toggle",
        meta={"enabled": bool(value)},
    )
    return bool(value)


async def has_access(session: AsyncSession, user: User) -> bool:
    """True when the user may use gated features (AI + test submission)."""
    if not await is_enabled(session):
        return True
    return user.subscription_active()


async def plans(session: AsyncSession) -> list[dict]:
    return await settings_store.subscription_plans(session)


async def get_plan(session: AsyncSession, key: str) -> dict | None:
    for plan in await plans(session):
        if plan.get("key") == key:
            return plan
    return None


async def set_plans(session: AsyncSession, new_plans: list[dict], *, by: int | None) -> None:
    cleaned = []
    for p in new_plans:
        try:
            cleaned.append(
                {
                    "key": str(p["key"]).strip()[:32],
                    "days": max(1, int(p["days"])),
                    "stars": max(1, int(p["stars"])),
                    "title_i18n": p.get("title_i18n") or {"uz": str(p.get("title", p["key"]))},
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    await settings_store.set(session, "subscription_plans", cleaned)
    await audit.record(session, actor_tg_id=by, action="subscription.plans", meta={"count": len(cleaned)})


async def extend(
    session: AsyncSession,
    user: User,
    *,
    days: int,
    plan_key: str,
    stars: int,
    charge_id: str,
) -> User:
    """Apply a successful payment: extend the subscription and record it (idempotent)."""
    existing = (
        await session.execute(
            select(Payment).where(Payment.telegram_payment_charge_id == charge_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return user

    base = user.subscription_until
    now = utcnow()
    if base is None or base < now:
        base = now
    user.subscription_until = base + timedelta(days=days)
    session.add(
        Payment(
            user_id=user.id,
            telegram_payment_charge_id=charge_id,
            stars_amount=stars,
            plan_key=plan_key,
            days=days,
        )
    )
    await session.flush()
    await audit.record(
        session,
        actor_tg_id=user.tg_id,
        action="subscription.paid",
        target=plan_key,
        meta={"days": days, "stars": stars, "until": user.subscription_until.isoformat()},
    )
    return user


async def mark_refunded(session: AsyncSession, charge_id: str, *, by: int | None) -> bool:
    payment = (
        await session.execute(
            select(Payment).where(Payment.telegram_payment_charge_id == charge_id)
        )
    ).scalar_one_or_none()
    if payment is None:
        return False
    payment.refunded = True
    user = await session.get(User, payment.user_id)
    if user and user.subscription_until:
        user.subscription_until = user.subscription_until - timedelta(days=payment.days)
    await session.flush()
    await audit.record(
        session, actor_tg_id=by, action="subscription.refund", target=charge_id
    )
    return True
