"""Shared response shaping."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import subscriptions as subs_svc


async def me_payload(session: AsyncSession, user: User) -> dict:
    sub_enabled = await subs_svc.is_enabled(session)
    return {
        "tg_id": user.tg_id,
        "name": user.full_name,
        "username": user.username,
        "language": user.language,
        "role": user.role,
        "status": user.status,
        "is_staff": user.is_staff,
        "is_owner": user.is_owner,
        "subscription": {
            "feature_enabled": sub_enabled,
            "active": user.subscription_active(),
            "until": user.subscription_until.isoformat() if user.subscription_until else None,
            "has_access": (not sub_enabled) or user.subscription_active(),
        },
    }


def application_dto(app) -> dict:
    return {
        "id": app.id,
        "tg_id": app.tg_id,
        "username": app.username,
        "full_name": app.full_name,
        "phone": app.phone,
        "language": app.language,
        "status": app.status,
        "created_at": app.created_at.isoformat() if app.created_at else None,
    }


def user_dto(user: User) -> dict:
    return {
        "tg_id": user.tg_id,
        "name": user.full_name,
        "username": user.username,
        "phone": user.phone,
        "language": user.language,
        "role": user.role,
        "status": user.status,
        "subscription_until": user.subscription_until.isoformat() if user.subscription_until else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
