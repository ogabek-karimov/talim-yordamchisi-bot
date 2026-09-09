"""Dispatcher assembly + webhook / polling helpers."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.types import BotCommand, Update

from app.bot.handlers import build_router
from app.bot.middlewares import ContextMiddleware
from app.config import settings

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="Start / restart"),
    BotCommand(command="language", description="Change language / Til / Язык"),
    BotCommand(command="apply", description="Submit an application"),
    BotCommand(command="subscription_status", description="My subscription"),
    BotCommand(command="help", description="Help"),
]


def build_dispatcher(storage: BaseStorage) -> Dispatcher:
    dp = Dispatcher(storage=storage)
    ctx = ContextMiddleware()
    dp.message.outer_middleware(ctx)
    dp.callback_query.outer_middleware(ctx)
    dp.pre_checkout_query.outer_middleware(ctx)
    dp.include_router(build_router())
    return dp


async def feed_update(bot: Bot, dp: Dispatcher, payload: dict) -> None:
    await dp.feed_update(bot, Update.model_validate(payload, context={"bot": bot}))


async def on_startup(bot: Bot) -> None:
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception:  # pragma: no cover
        logger.exception("set_my_commands failed")
    if settings.use_polling or not settings.webhook_url:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("polling mode (no webhook set)")
        return
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret,
        allowed_updates=["message", "callback_query", "pre_checkout_query"],
        drop_pending_updates=False,
    )
    logger.info("webhook set: %s", settings.webhook_url)
