"""FastAPI application: serves the bot webhook, the Mini App, and the JSON API."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import WEBAPP_DIR, settings
from app.db import init_models, session_scope

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

_polling_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _polling_task

    await init_models()
    async with session_scope() as session:
        from app.services import settings_store
        from app.services import users as users_svc

        await users_svc.ensure_owner(session)
        await settings_store.ensure_defaults(session)

    from app.bot.dispatcher import on_startup
    from app.bot.instance import get_bot, get_dispatcher

    bot = get_bot()
    if bot is not None:
        dp = get_dispatcher()
        app.state.bot = bot
        app.state.dp = dp
        await on_startup(bot)
        if settings.use_polling or not settings.webhook_url:
            logger.info("starting long-polling")
            _polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    else:
        app.state.bot = None
        logger.warning("bot disabled (no valid BOT_TOKEN)")

    try:
        yield
    finally:
        if _polling_task:
            _polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _polling_task
        if getattr(app.state, "bot", None) is not None:
            await app.state.bot.session.close()


app = FastAPI(title="Ta'lim yordamchisi", lifespan=lifespan, docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API routers ---------------------------------------------
from app.api import admin, ai, auth, pay, student  # noqa: E402

for r in (auth.router, student.router, ai.router, pay.router, admin.router):
    app.include_router(r)


# --- health -------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "bot": getattr(app.state, "bot", None) is not None}


@app.get("/")
async def root() -> Response:
    return Response(status_code=302, headers={"Location": "/app/"})


# --- Telegram webhook --------------------------------------
@app.post(settings.webhook_path)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> Response:
    from app.security import check_webhook_secret

    if not check_webhook_secret(x_telegram_bot_api_secret_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "bad secret")
    bot = getattr(app.state, "bot", None)
    if bot is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "bot disabled")
    payload = await request.json()
    from app.bot.dispatcher import feed_update

    await feed_update(bot, app.state.dp, payload)
    return Response(status_code=200)


# --- Mini App static files (mounted last so it doesn't shadow /api) ---
if WEBAPP_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")
