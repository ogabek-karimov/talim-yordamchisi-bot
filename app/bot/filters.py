"""Helpers to match localized button text across all supported languages."""
from __future__ import annotations

from aiogram.types import Message

from app.i18n import SUPPORTED, t


def _variants(*keys: str) -> set[str]:
    out: set[str] = set()
    for key in keys:
        for lang in SUPPORTED:
            out.add(t(key, lang))
    return out


def text_is(*keys: str):
    wanted = _variants(*keys)

    def _check(message: Message) -> bool:
        return bool(message.text and message.text.strip() in wanted)

    return _check
