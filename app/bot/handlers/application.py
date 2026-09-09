"""Access application ("ariza") flow: name -> phone -> confirm."""
from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import text_is
from app.bot.keyboards import apply_confirm, application_decision, main_menu, phone_request
from app.bot.states import ApplyForm
from app.i18n import t
from app.models import User
from app.services import applications as apps_svc
from app.services import users as users_svc

logger = logging.getLogger(__name__)
router = Router(name="application")

_PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{6,20}$")


async def _notify_staff(session: AsyncSession, app_id: int, app) -> None:
    from app.services.notifications import dm

    for staff in await users_svc.staff_users(session):
        text = t(
            "staff.new_application",
            staff.language,
            name=app.full_name,
            phone=app.phone,
            tg_id=app.tg_id,
            username=app.username or "-",
            language=app.language,
        )
        await dm(
            staff.tg_id,
            text,
            reply_markup=application_decision(app_id, staff.language),
        )


@router.message(Command("apply"))
@router.message(text_is("menu.btn_apply"))
async def start_apply(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    lang = user.language
    if user.is_approved:
        await message.answer(t("apply.already_approved", lang), reply_markup=main_menu(user))
        return
    if await apps_svc.pending_for(session, user.tg_id):
        await message.answer(t("apply.already_pending", lang), reply_markup=main_menu(user))
        return
    await state.set_state(ApplyForm.name)
    await message.answer(t("apply.intro", lang))
    await message.answer(t("apply.ask_name", lang))


@router.message(text_is("apply.btn_cancel", "common.cancel"))
async def cancel_apply(message: Message, user: User, state: FSMContext) -> None:
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer(t("apply.cancelled", user.language), reply_markup=main_menu(user))


@router.message(ApplyForm.name, F.text)
async def apply_name(message: Message, user: User, state: FSMContext) -> None:
    lang = user.language
    name = (message.text or "").strip()
    if len(name) < 3:
        await message.answer(t("apply.name_too_short", lang))
        return
    await state.update_data(name=name)
    await state.set_state(ApplyForm.phone)
    await message.answer(t("apply.ask_phone", lang), reply_markup=phone_request(lang))


@router.message(ApplyForm.phone, F.contact)
async def apply_phone_contact(message: Message, user: User, state: FSMContext) -> None:
    await _store_phone(message, user, state, message.contact.phone_number)


@router.message(ApplyForm.phone, F.text)
async def apply_phone_text(message: Message, user: User, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not _PHONE_RE.match(text):
        await message.answer(t("apply.ask_phone", user.language), reply_markup=phone_request(user.language))
        return
    await _store_phone(message, user, state, text)


async def _store_phone(message: Message, user: User, state: FSMContext, phone: str) -> None:
    lang = user.language
    data = await state.get_data()
    await state.update_data(phone=phone)
    await state.set_state(ApplyForm.confirm)
    await message.answer(
        t("apply.confirm", lang, name=data.get("name", "-"), phone=phone),
        reply_markup=apply_confirm(lang),
    )


@router.message(ApplyForm.confirm, text_is("apply.btn_restart"))
async def apply_restart(message: Message, user: User, state: FSMContext) -> None:
    await state.set_state(ApplyForm.name)
    await message.answer(t("apply.ask_name", user.language))


@router.message(ApplyForm.confirm, text_is("apply.btn_confirm", "common.done"))
async def apply_submit(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    lang = user.language
    data = await state.get_data()
    name, phone = data.get("name"), data.get("phone")
    if not name or not phone:
        await state.set_state(ApplyForm.name)
        await message.answer(t("apply.ask_name", lang))
        return
    app = await apps_svc.create(
        session,
        tg_id=user.tg_id,
        username=user.username,
        full_name=name,
        phone=phone,
        language=lang,
    )
    await state.clear()
    await message.answer(t("apply.submitted", lang), reply_markup=main_menu(user))
    try:
        await _notify_staff(session, app.id, app)
    except Exception:  # pragma: no cover
        logger.exception("failed to notify staff about application %s", app.id)


@router.message(ApplyForm.confirm, F.text)
async def apply_confirm_other(message: Message, user: User, state: FSMContext) -> None:
    lang = user.language
    data = await state.get_data()
    await message.answer(
        t("apply.confirm", lang, name=data.get("name", "-"), phone=data.get("phone", "-")),
        reply_markup=apply_confirm(lang),
    )
