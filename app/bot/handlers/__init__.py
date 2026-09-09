"""Aiogram routers, registered in order."""
from __future__ import annotations

from aiogram import Router

from app.bot.handlers import (
    admin,
    application,
    menu,
    payments,
    start,
)


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(application.router)
    root.include_router(payments.router)
    root.include_router(admin.router)
    root.include_router(menu.router)  # menu last: contains broad fallbacks
    return root
