"""Manually (re)set or delete the Telegram webhook.

Usage:
    python -m scripts.set_webhook set     # set to $WEBHOOK_BASE$WEBHOOK_PATH
    python -m scripts.set_webhook delete
    python -m scripts.set_webhook info
"""
from __future__ import annotations

import asyncio
import sys

from aiogram import Bot

from app.config import settings


async def main(action: str) -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set")
    bot = Bot(settings.bot_token)
    try:
        if action == "set":
            if not settings.webhook_url:
                raise SystemExit("WEBHOOK_BASE is not set")
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
                allowed_updates=["message", "callback_query", "pre_checkout_query"],
            )
            print("webhook set ->", settings.webhook_url)
        elif action == "delete":
            await bot.delete_webhook(drop_pending_updates=False)
            print("webhook deleted")
        elif action == "info":
            info = await bot.get_webhook_info()
            print(info.model_dump_json(indent=2))
        else:
            raise SystemExit(f"unknown action: {action}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "info"))
