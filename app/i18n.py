"""Tiny JSON-catalog i18n helper.

Catalogs live in ``app/locales/<lang>.json`` as flat ``{key: text}`` maps.
Lookup falls back:  requested lang  ->  Uzbek (``uz``)  ->  the key itself.
"""
from __future__ import annotations

import json
from functools import lru_cache

from app.config import LOCALES_DIR, settings

SUPPORTED = settings.SUPPORTED_LANGUAGES
FALLBACK = "uz"

# Human-facing language names (shown in the language picker).
LANGUAGE_NAMES: dict[str, str] = {
    "uz": "🇺🇿 O‘zbekcha",
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "kaa": "🟢 Qaraqalpaqsha",
}


@lru_cache
def _catalogs() -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    for lang in SUPPORTED:
        path = LOCALES_DIR / f"{lang}.json"
        if path.exists():
            data[lang] = json.loads(path.read_text(encoding="utf-8"))
        else:
            data[lang] = {}
    return data


def normalize_lang(lang: str | None) -> str:
    lang = (lang or "").lower().replace("-", "_").split("_")[0]
    if lang == "uz":
        return "uz"
    return lang if lang in SUPPORTED else settings.default_lang


def t(key: str, lang: str | None = None, /, **kwargs: object) -> str:
    lang = normalize_lang(lang)
    cats = _catalogs()
    text = cats.get(lang, {}).get(key)
    if text is None:
        text = cats.get(FALLBACK, {}).get(key)
    if text is None:
        return key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def catalog(lang: str) -> dict[str, str]:
    """Full merged catalog for a language (fallback filled in) — used by the Mini App."""
    lang = normalize_lang(lang)
    cats = _catalogs()
    merged = dict(cats.get(FALLBACK, {}))
    merged.update(cats.get(lang, {}))
    return merged


def all_keys() -> set[str]:
    keys: set[str] = set()
    for cat in _catalogs().values():
        keys |= set(cat.keys())
    return keys


def missing_keys() -> dict[str, list[str]]:
    """Per-language list of keys present somewhere but missing there (for tests)."""
    everything = all_keys()
    out: dict[str, list[str]] = {}
    for lang, cat in _catalogs().items():
        gap = sorted(everything - set(cat.keys()))
        if gap:
            out[lang] = gap
    return out
