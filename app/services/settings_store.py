"""Runtime settings stored in the ``settings`` KV table.

These are toggled by staff at runtime (e.g. the subscription feature on/off)
and therefore must live in the DB, not the environment.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting

# key -> default value
DEFAULTS: dict[str, Any] = {
    "subscription_enabled": False,
    "subscription_plans": [
        {"key": "m1", "days": 30, "stars": 150, "title_i18n": {
            "uz": "1 oy", "ru": "1 месяц", "en": "1 month", "kaa": "1 ay"}},
        {"key": "m3", "days": 90, "stars": 400, "title_i18n": {
            "uz": "3 oy", "ru": "3 месяца", "en": "3 months", "kaa": "3 ay"}},
    ],
}


async def get(session: AsyncSession, key: str, default: Any = None) -> Any:
    row = await session.get(Setting, key)
    if row is None:
        return DEFAULTS.get(key, default)
    return row.value


async def set(session: AsyncSession, key: str, value: Any) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    await session.flush()


async def all_settings(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(Setting))).scalars().all()
    out = dict(DEFAULTS)
    for r in rows:
        out[r.key] = r.value
    return out


async def ensure_defaults(session: AsyncSession) -> None:
    for key, value in DEFAULTS.items():
        if await session.get(Setting, key) is None:
            session.add(Setting(key=key, value=value))
    await session.flush()


async def subscription_enabled(session: AsyncSession) -> bool:
    return bool(await get(session, "subscription_enabled", False))


async def subscription_plans(session: AsyncSession) -> list[dict]:
    plans = await get(session, "subscription_plans", [])
    return plans if isinstance(plans, list) else []
