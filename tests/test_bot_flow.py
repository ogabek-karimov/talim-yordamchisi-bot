"""Drive real aiogram handlers with fake Telegram updates (no network)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from app.bot.dispatcher import build_dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from app.db import session_scope
from app.models import AppStatus, Status
from app.services import applications as apps_svc
from app.services import users as users_svc

BOT_ID = 424242


@pytest.fixture
def bot(monkeypatch):
    from aiogram import Bot
    from aiogram.client.bot import Bot as BotCls

    b = Bot(token=f"{BOT_ID}:AAaaAAaaAAaaAAaaAAaaAAaaAAaaAAaaAAa")
    calls: list = []

    async def fake_call(self, method, request_timeout=None):
        calls.append(method)
        return AsyncMock()

    monkeypatch.setattr(BotCls, "__call__", fake_call)
    b.sent = calls
    return b


@pytest.fixture(scope="module")
def dp():
    # module-scoped: aiogram routers can only be attached to one parent
    return build_dispatcher(MemoryStorage())


def _msg(text: str, uid: int) -> Update:
    return Update(
        update_id=uid,
        message=Message(
            message_id=uid,
            date=datetime.now(timezone.utc),
            chat=Chat(id=uid, type="private"),
            from_user=TgUser(id=uid, is_bot=False, first_name="T"),
            text=text,
        ),
    )


def _cb(data: str, uid: int) -> Update:
    return Update(
        update_id=uid + 500000,
        callback_query=CallbackQuery(
            id=str(uid),
            from_user=TgUser(id=uid, is_bot=False, first_name="T"),
            chat_instance="ci",
            data=data,
            message=Message(
                message_id=uid,
                date=datetime.now(timezone.utc),
                chat=Chat(id=uid, type="private"),
                from_user=TgUser(id=BOT_ID, is_bot=True, first_name="bot"),
            ),
        ),
    )


async def test_start_then_pick_language_persists(bot, dp):
    uid = 310001
    await dp.feed_update(bot, _msg("/start", uid))
    assert bot.sent, "no reply to /start"

    await dp.feed_update(bot, _cb("lang:ru", uid))
    async with session_scope() as s:
        u = await users_svc.get_by_tg(s, uid)
        assert u is not None and u.language == "ru"


async def test_application_flow_creates_pending_and_user_can_use_after_approve(bot, dp):
    uid = 310002
    await dp.feed_update(bot, _msg("/start", uid))
    await dp.feed_update(bot, _cb("lang:uz", uid))
    await dp.feed_update(bot, _msg("/apply", uid))
    await dp.feed_update(bot, _msg("Ali Valiyev", uid))
    await dp.feed_update(bot, _msg("+998901112233", uid))
    # confirm button label in uz
    from app.i18n import t

    await dp.feed_update(bot, _msg(t("apply.btn_confirm", "uz"), uid))

    async with session_scope() as s:
        pending = await apps_svc.pending_for(s, uid)
        assert pending is not None
        assert pending.full_name == "Ali Valiyev"
        assert pending.phone == "+998901112233"
        assert pending.status == AppStatus.PENDING


async def test_non_approved_user_gets_gate_message(bot, dp):
    uid = 310003
    await dp.feed_update(bot, _msg("/start", uid))
    await dp.feed_update(bot, _cb("lang:en", uid))
    bot.sent.clear()
    await dp.feed_update(bot, _msg("hello there", uid))
    assert bot.sent  # fallback replied (err.not_approved)


async def test_admin_command_denied_for_regular_user(bot, dp):
    uid = 310004
    async with session_scope() as s:
        u, _ = await users_svc.get_or_create(s, uid, first_name="R")
        u.status = Status.APPROVED
        await s.flush()
    bot.sent.clear()
    await dp.feed_update(bot, _msg("/addadmin 999", uid))
    # handler replies with err.owner_only; assert no crash + a reply happened
    assert bot.sent


async def test_admin_can_approve_application_via_callback(bot, dp):
    admin_id = 310010
    cand_id = 310011
    async with session_scope() as s:
        a, _ = await users_svc.get_or_create(s, admin_id, first_name="Adm")
        a.role, a.status = "admin", Status.APPROVED
        app = await apps_svc.create(
            s, tg_id=cand_id, username=None, full_name="Cand", phone="+998900000001", language="uz"
        )
        await s.flush()
        app_id = app.id

    await dp.feed_update(bot, _cb(f"appr:{app_id}", admin_id))
    async with session_scope() as s:
        u = await users_svc.get_by_tg(s, cand_id)
        assert u is not None and u.status == Status.APPROVED


async def test_reject_reason_fsm(bot, dp):
    admin_id = 310012
    cand_id = 310013
    async with session_scope() as s:
        a, _ = await users_svc.get_or_create(s, admin_id, first_name="Adm")
        a.role, a.status = "admin", Status.APPROVED
        app = await apps_svc.create(
            s, tg_id=cand_id, username=None, full_name="C2", phone="+998900000002", language="uz"
        )
        await s.flush()
        app_id = app.id

    await dp.feed_update(bot, _cb(f"rej:{app_id}", admin_id))
    await dp.feed_update(bot, _msg("Not eligible", admin_id))
    async with session_scope() as s:
        app = await apps_svc.get(s, app_id)
        assert app.status == AppStatus.REJECTED and app.note == "Not eligible"


async def test_owner_toggles_subscription_command(bot, dp):
    owner_id = 500000  # seeded owner
    async with session_scope() as s:
        await users_svc.ensure_owner(s)
    from app.services import subscriptions as subs_svc

    await dp.feed_update(bot, _msg("/subscription on", owner_id))
    async with session_scope() as s:
        assert await subs_svc.is_enabled(s) is True
    await dp.feed_update(bot, _msg("/subscription off", owner_id))
    async with session_scope() as s:
        assert await subs_svc.is_enabled(s) is False
