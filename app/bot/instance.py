"""Lazily-constructed singleton Bot + Dispatcher."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dp: Dispatcher | None = None


def get_bot() -> Bot | None:
    global _bot
    if _bot is None:
        if not settings.bot_token or ":" not in settings.bot_token:
            logger.warning("BOT_TOKEN missing/invalid — bot features disabled")
            return None
        _bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
        )
    return _bot


def get_dispatcher() -> Dispatcher:
    global _dp
    if _dp is None:
        from app.bot.dispatcher import build_dispatcher

        _dp = build_dispatcher(MemoryStorage())
    return _dp
