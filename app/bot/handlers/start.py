"""/start, language selection, /language."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import text_is
from app.bot.keyboards import language_inline, main_menu
from app.i18n import SUPPORTED, t
from app.models import Status, User
from app.services import users as users_svc

router = Router(name="start")


async def _send_menu(message: Message, user: User) -> None:
    lang = user.language
    if user.status == Status.BLOCKED:
        await message.answer(t("menu.blocked", lang), reply_markup=main_menu(user))
        return
    if user.is_approved:
        await message.answer(t("menu.title_approved", lang), reply_markup=main_menu(user))
    else:
        await message.answer(t("menu.pending", lang), reply_markup=main_menu(user))


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        t("start.greeting", user.language), reply_markup=language_inline()
    )


@router.message(Command("language"))
@router.message(text_is("menu.btn_language", "lang.button"))
async def cmd_language(message: Message, user: User) -> None:
    await message.answer(
        t("start.choose_language", user.language), reply_markup=language_inline()
    )


@router.callback_query(F.data.startswith("lang:"))
async def on_language_pick(
    call: CallbackQuery, user: User, session: AsyncSession, state: FSMContext
) -> None:
    code = call.data.split(":", 1)[1]
    if code not in SUPPORTED:
        await call.answer()
        return
    await users_svc.set_language(session, user, code)
    await call.answer()
    if call.message:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.message.answer(t("lang.updated", code))
    await _send_menu(call.message, user)
