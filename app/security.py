"""Telegram Mini App auth: initData HMAC validation + short-lived session tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from app.config import settings


class AuthError(Exception):
    """Raised when initData or a session token fails validation."""


# --- Telegram initData -------------------------------------------------
def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def validate_init_data(
    init_data: str,
    *,
    bot_token: str | None = None,
    max_age: int | None = None,
) -> dict[str, Any]:
    """Validate a Telegram WebApp ``initData`` string.

    Returns the parsed fields (with ``user`` decoded to a dict) on success,
    raises :class:`AuthError` otherwise.
    """
    bot_token = bot_token or settings.bot_token
    max_age = settings.initdata_ttl if max_age is None else max_age
    if not init_data:
        raise AuthError("empty initData")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise AuthError("missing hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    calc_hash = hmac.new(
        _secret_key(bot_token), data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        raise AuthError("bad hash")

    auth_date = int(pairs.get("auth_date", "0") or "0")
    if max_age and (time.time() - auth_date) > max_age:
        raise AuthError("initData expired")

    out: dict[str, Any] = dict(pairs)
    if "user" in out:
        try:
            out["user"] = json.loads(out["user"])
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise AuthError("bad user json") from exc
    return out


# --- session tokens --------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_session(tg_id: int, *, ttl: int | None = None, extra: dict | None = None) -> str:
    ttl = settings.session_ttl if ttl is None else ttl
    payload = {"uid": int(tg_id), "exp": int(time.time()) + ttl}
    if extra:
        payload.update(extra)
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(
        hmac.new(settings.session_secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    return f"{body}.{sig}"


def verify_session(token: str) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise AuthError("malformed token") from exc
    expected = _b64e(
        hmac.new(settings.session_secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig):
        raise AuthError("bad signature")
    payload = json.loads(_b64d(body))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthError("token expired")
    return payload


# --- webhook secret header ----------------------------------------
def check_webhook_secret(header_value: str | None) -> bool:
    return hmac.compare_digest(header_value or "", settings.webhook_secret)
