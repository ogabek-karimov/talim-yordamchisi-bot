"""Outer middleware: DB session + resolved User for every update."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from app.db import session_scope
from app.services import users as users_svc


class ContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user") or getattr(
            event, "from_user", None
        )
        async with session_scope() as session:
            data["session"] = session
            if tg_user is not None and not tg_user.is_bot:
                user, _ = await users_svc.get_or_create(
                    session,
                    tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                )
                data["user"] = user
            return await handler(event, data)
