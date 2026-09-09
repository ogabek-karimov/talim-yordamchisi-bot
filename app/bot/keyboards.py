"""Role-aware keyboards. Regular users never see staff buttons."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.config import settings
from app.i18n import LANGUAGE_NAMES, t
from app.models import User


def language_inline() -> InlineKeyboardMarkup:
    rows, row = [], []
    for code, label in LANGUAGE_NAMES.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"lang:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _webapp_button(lang: str, path: str = "") -> KeyboardButton | None:
    url = settings.webapp_url
    if not url:
        return None
    if path:
        url = f"{url}?{path}"
    return KeyboardButton(text=t("menu.btn_open_app", lang), web_app=WebAppInfo(url=url))


def main_menu(user: User) -> ReplyKeyboardMarkup:
    lang = user.language
    rows: list[list[KeyboardButton]] = []

    if user.is_approved:
        app_btn = _webapp_button(lang)
        if app_btn:
            rows.append([app_btn])
        if user.is_staff:
            admin_btn = _webapp_button(lang, "view=admin")
            if admin_btn:
                admin_btn.text = t("menu.btn_admin", lang)
                rows.append([admin_btn])
        rows.append(
            [
                KeyboardButton(text=t("menu.btn_subscription", lang)),
                KeyboardButton(text=t("menu.btn_language", lang)),
            ]
        )
        rows.append([KeyboardButton(text=t("menu.btn_help", lang))])
    else:
        rows.append([KeyboardButton(text=t("menu.btn_apply", lang))])
        rows.append(
            [
                KeyboardButton(text=t("menu.btn_language", lang)),
                KeyboardButton(text=t("menu.btn_help", lang)),
            ]
        )

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_request(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("apply.phone_button", lang), request_contact=True)],
            [KeyboardButton(text=t("apply.btn_cancel", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def apply_confirm(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("apply.btn_confirm", lang))],
            [
                KeyboardButton(text=t("apply.btn_restart", lang)),
                KeyboardButton(text=t("apply.btn_cancel", lang)),
            ],
        ],
        resize_keyboard=True,
    )


def application_decision(app_id: int, lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("staff.btn_approve", lang), callback_data=f"appr:{app_id}"
                ),
                InlineKeyboardButton(
                    text=t("staff.btn_reject", lang), callback_data=f"rej:{app_id}"
                ),
            ]
        ]
    )


def subscription_plans_inline(plans: list[dict], lang: str) -> InlineKeyboardMarkup:
    from app.services.testbank import pick

    rows = []
    for plan in plans:
        title = pick(plan.get("title_i18n"), lang) or plan.get("key", "")
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("sub.plan_line", lang, title=title, days=plan["days"], stars=plan["stars"]),
                    callback_data=f"buy:{plan['key']}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
