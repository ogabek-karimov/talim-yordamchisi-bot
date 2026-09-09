"""Help button + catch-all fallback. Registered last."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.filters import text_is
from app.bot.keyboards import main_menu
from app.i18n import t
from app.models import Status, User

router = Router(name="menu")


@router.message(Command("help"))
@router.message(text_is("menu.btn_help"))
async def cmd_help(message: Message, user: User) -> None:
    await message.answer(t("help.text", user.language), reply_markup=main_menu(user))


@router.message(F.text)
async def fallback(message: Message, user: User, state: FSMContext) -> None:
    if await state.get_state() is not None:
        return  # let the active FSM flow re-prompt on its own terms
    lang = user.language
    if user.status == Status.BLOCKED:
        await message.answer(t("menu.blocked", lang))
        return
    if user.is_approved:
        await message.answer(t("menu.title_approved", lang), reply_markup=main_menu(user))
    else:
        await message.answer(t("err.not_approved", lang), reply_markup=main_menu(user))
