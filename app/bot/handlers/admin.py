"""Staff commands + application approve/reject callbacks."""
from __future__ import annotations

import logging
import time

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import RejectForm
from app.i18n import t
from app.models import Role, User
from app.services import applications as apps_svc
from app.services import subscriptions as subs_svc
from app.services import users as users_svc
from app.services.notifications import dm

logger = logging.getLogger(__name__)
router = Router(name="admin")

# owner tg_id -> (target tg_id, expires_at)
_pending_transfer: dict[int, tuple[int, float]] = {}


def _staff_only(user: User) -> bool:
    return user.is_staff and user.is_approved


def _parse_id(text: str | None) -> int | None:
    if not text:
        return None
    token = text.strip().split()[0]
    return int(token) if token.lstrip("-").isdigit() else None


# --- applications --------------------------------------------------
@router.message(Command("pending"))
async def cmd_pending(message: Message, user: User, session: AsyncSession) -> None:
    if not _staff_only(user):
        await message.answer(t("err.admin_only", user.language))
        return
    from app.bot.keyboards import application_decision

    pending = await apps_svc.list_pending(session)
    if not pending:
        await message.answer(t("app.admin.apps_empty", user.language))
        return
    for app in pending:
        await message.answer(
            t(
                "staff.new_application",
                user.language,
                name=app.full_name,
                phone=app.phone,
                tg_id=app.tg_id,
                username=app.username or "-",
                language=app.language,
            ),
            reply_markup=application_decision(app.id, user.language),
        )


@router.callback_query(F.data.startswith("appr:"))
async def cb_approve(call: CallbackQuery, user: User, session: AsyncSession) -> None:
    if not _staff_only(user):
        await call.answer(t("err.admin_only", user.language), show_alert=True)
        return
    app_id = int(call.data.split(":", 1)[1])
    app = await apps_svc.get(session, app_id)
    if app is None or app.status != "pending":
        await call.answer(t("staff.already_decided", user.language), show_alert=True)
        return
    await apps_svc.approve(session, app_id, by=user.tg_id)
    await call.answer(t("staff.approved_done", user.language, name=app.full_name))
    if call.message:
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(t("staff.approved_done", user.language, name=app.full_name))
    await dm(app.tg_id, t("notify.approved", app.language))


@router.callback_query(F.data.startswith("rej:"))
async def cb_reject(call: CallbackQuery, user: User, state: FSMContext) -> None:
    if not _staff_only(user):
        await call.answer(t("err.admin_only", user.language), show_alert=True)
        return
    app_id = int(call.data.split(":", 1)[1])
    await state.set_state(RejectForm.reason)
    await state.update_data(app_id=app_id)
    await call.answer()
    if call.message:
        await call.message.answer(t("staff.reject_reason_prompt", user.language))


@router.message(RejectForm.reason, F.text)
async def reject_reason(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    app_id = int(data.get("app_id", 0))
    await state.clear()
    reason = None if (message.text or "").strip() in ("/skip", "-") else message.text.strip()
    app = await apps_svc.get(session, app_id)
    if app is None or app.status != "pending":
        await message.answer(t("staff.already_decided", user.language))
        return
    await apps_svc.reject(session, app_id, by=user.tg_id, reason=reason)
    await message.answer(t("staff.rejected_done", user.language, name=app.full_name))
    dm_text = (
        t("notify.rejected", app.language, reason=reason)
        if reason
        else t("notify.rejected_no_reason", app.language)
    )
    await dm(app.tg_id, dm_text)


# --- user management -------------------------------------------
@router.message(Command("adduser"))
async def cmd_adduser(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not _staff_only(user):
        await message.answer(t("err.admin_only", user.language))
        return
    tg_id = _parse_id(command.args)
    if tg_id is None:
        await message.answer(t("cmd.adduser_usage", user.language))
        return
    name = None
    if command.args and len(command.args.split(maxsplit=1)) > 1:
        name = command.args.split(maxsplit=1)[1]
    _, already = await users_svc.add_manual(session, tg_id, by=user.tg_id, name=name)
    if already:
        await message.answer(t("cmd.adduser_exists", user.language))
    else:
        await message.answer(t("cmd.adduser_done", user.language, tg_id=tg_id))
        await dm(tg_id, t("notify.added_by_admin", "uz"))


@router.message(Command("removeuser"))
async def cmd_removeuser(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not _staff_only(user):
        await message.answer(t("err.admin_only", user.language))
        return
    tg_id = _parse_id(command.args)
    if tg_id is None:
        await message.answer(t("cmd.removeuser_usage", user.language))
        return
    result = await users_svc.remove(session, tg_id, by=user.tg_id)
    if result is None:
        await message.answer(t("cmd.user_not_found", user.language))
    else:
        await message.answer(t("cmd.removeuser_done", user.language, tg_id=tg_id))
        await dm(tg_id, t("notify.blocked", result.language))


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not user.is_owner:
        await message.answer(t("err.owner_only", user.language))
        return
    tg_id = _parse_id(command.args)
    if tg_id is None:
        await message.answer(t("cmd.addadmin_usage", user.language))
        return
    await users_svc.make_admin(session, tg_id, by=user.tg_id)
    await message.answer(t("cmd.addadmin_done", user.language, tg_id=tg_id))
    await dm(tg_id, t("notify.role_promoted_admin", "uz"))


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not user.is_owner:
        await message.answer(t("err.owner_only", user.language))
        return
    tg_id = _parse_id(command.args)
    if tg_id is None:
        await message.answer(t("cmd.removeadmin_usage", user.language))
        return
    await users_svc.remove_admin(session, tg_id, by=user.tg_id)
    await message.answer(t("cmd.removeadmin_done", user.language, tg_id=tg_id))
    await dm(tg_id, t("notify.role_demoted", "uz"))


@router.message(Command("transfer_ownership"))
async def cmd_transfer(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not user.is_owner:
        await message.answer(t("err.owner_only", user.language))
        return
    parts = (command.args or "").split()
    if not parts or not parts[0].lstrip("-").isdigit():
        await message.answer(t("cmd.transfer_usage", user.language))
        return
    target = int(parts[0])
    target_user = await users_svc.get_by_tg(session, target)
    if target_user is None or target_user.role != Role.ADMIN:
        await message.answer(t("cmd.transfer_not_admin", user.language))
        return
    confirmed = len(parts) > 1 and parts[1].upper() == "CONFIRM"
    pending = _pending_transfer.get(user.tg_id)
    if not (confirmed and pending and pending[0] == target and pending[1] > time.time()):
        _pending_transfer[user.tg_id] = (target, time.time() + 30)
        await message.answer(t("cmd.transfer_confirm", user.language, tg_id=target))
        return
    _pending_transfer.pop(user.tg_id, None)
    await users_svc.transfer_ownership(session, target, by=user.tg_id)
    await message.answer(t("cmd.transfer_done", user.language))
    await dm(target, t("notify.ownership_received", target_user.language))


# --- subscription toggle -------------------------------------
@router.message(Command("subscription"))
async def cmd_subscription(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not _staff_only(user):
        await message.answer(t("err.admin_only", user.language))
        return
    arg = (command.args or "").strip().lower()
    if arg in ("on", "off"):
        enabled = await subs_svc.set_enabled(session, arg == "on", by=user.tg_id)
        state = t("cmd.sub_on", user.language) if enabled else t("cmd.sub_off", user.language)
        await message.answer(t("cmd.sub_toggled", user.language, state=state))
    else:
        enabled = await subs_svc.is_enabled(session)
        state = t("cmd.sub_on", user.language) if enabled else t("cmd.sub_off", user.language)
        await message.answer(t("cmd.sub_status", user.language, state=state))


@router.message(Command("refund"))
async def cmd_refund(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not _staff_only(user):
        await message.answer(t("err.admin_only", user.language))
        return
    charge_id = (command.args or "").strip()
    if not charge_id:
        await message.answer(t("cmd.refund_usage", user.language))
        return
    from app.bot.instance import get_bot

    bot = get_bot()
    try:
        payment = await subs_svc.mark_refunded(session, charge_id, by=user.tg_id)
        if not payment:
            await message.answer(t("cmd.user_not_found", user.language))
            return
        from app.models import Payment
        from sqlalchemy import select

        row = (
            await session.execute(
                select(Payment).where(Payment.telegram_payment_charge_id == charge_id)
            )
        ).scalar_one()
        target = await session.get(User, row.user_id)
        if bot and target:
            await bot.refund_star_payment(user_id=target.tg_id, telegram_payment_charge_id=charge_id)
        await message.answer(t("cmd.refund_done", user.language))
    except Exception as exc:  # pragma: no cover
        await message.answer(t("cmd.refund_failed", user.language, error=str(exc)))


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, user: User, session: AsyncSession, command: CommandObject) -> None:
    if not _staff_only(user):
        await message.answer(t("err.admin_only", user.language))
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer(t("cmd.broadcast_usage", user.language))
        return
    from app.services.broadcast import broadcast

    ok, total = await broadcast(session, text)
    await message.answer(t("cmd.broadcast_sent", user.language, ok=ok, total=total))
