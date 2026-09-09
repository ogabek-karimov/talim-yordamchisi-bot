"""Telegram Stars subscription purchase flow."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import text_is
from app.bot.keyboards import main_menu, subscription_plans_inline
from app.i18n import t
from app.models import User
from app.services import subscriptions as subs_svc
from app.services.testbank import pick

logger = logging.getLogger(__name__)
router = Router(name="payments")

PAYLOAD_PREFIX = "sub:"


def _fmt_until(user: User, lang: str) -> str:
    if not user.subscription_until:
        return "-"
    return user.subscription_until.strftime("%Y-%m-%d %H:%M UTC")


@router.message(Command("subscription_status"))
@router.message(text_is("menu.btn_subscription"))
async def show_subscription(message: Message, user: User, session: AsyncSession) -> None:
    lang = user.language
    if not user.is_approved:
        await message.answer(t("err.not_approved", lang))
        return
    if not await subs_svc.is_enabled(session):
        await message.answer(t("sub.disabled_globally", lang), reply_markup=main_menu(user))
        return
    if user.subscription_active():
        await message.answer(t("sub.status_active", lang, until=_fmt_until(user, lang)))
    else:
        await message.answer(t("sub.status_inactive", lang))
    plans = await subs_svc.plans(session)
    if plans:
        await message.answer(t("sub.buy_prompt", lang), reply_markup=subscription_plans_inline(plans, lang))


@router.callback_query(F.data.startswith("buy:"))
async def buy_plan(call: CallbackQuery, user: User, session: AsyncSession) -> None:
    lang = user.language
    key = call.data.split(":", 1)[1]
    plan = await subs_svc.get_plan(session, key)
    if plan is None or not await subs_svc.is_enabled(session):
        await call.answer(t("sub.pay_failed", lang), show_alert=True)
        return
    from app.bot.instance import get_bot

    bot = get_bot()
    if bot is None:
        await call.answer(t("err.generic", lang), show_alert=True)
        return
    title = pick(plan.get("title_i18n"), lang) or key
    await call.answer()
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=t("app.sub.extend", lang),
        description=t("sub.plan_line", lang, title=title, days=plan["days"], stars=plan["stars"]),
        payload=f"{PAYLOAD_PREFIX}{key}",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=int(plan["stars"]))],
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(message: Message, user: User, session: AsyncSession) -> None:
    lang = user.language
    sp = message.successful_payment
    payload = sp.invoice_payload or ""
    key = payload[len(PAYLOAD_PREFIX):] if payload.startswith(PAYLOAD_PREFIX) else ""
    plan = await subs_svc.get_plan(session, key)
    if plan is None:
        logger.warning("paid with unknown plan payload=%r", payload)
        await message.answer(t("sub.pay_failed", lang))
        return
    await subs_svc.extend(
        session,
        user,
        days=int(plan["days"]),
        plan_key=key,
        stars=int(sp.total_amount),
        charge_id=sp.telegram_payment_charge_id,
    )
    await message.answer(
        t("sub.pay_success", lang, until=_fmt_until(user, lang)),
        reply_markup=main_menu(user),
    )
