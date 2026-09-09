"""Fire-and-forget direct messages to users (best-effort)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def dm(tg_id: int, text: str, **kwargs) -> bool:
    """Send a DM to a user. Returns True on success, swallows Telegram errors."""
    from app.bot.instance import get_bot

    bot = get_bot()
    if bot is None:
        logger.warning("dm skipped: bot not initialised")
        return False
    try:
        await bot.send_message(tg_id, text, **kwargs)
        return True
    except Exception as exc:  # user blocked bot / never started / etc.
        logger.info("dm to %s failed: %s", tg_id, exc)
        return False
