import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.security import AuthError, validate_init_data

TOKEN = "123456:TEST-TOKEN"


def build_init_data(token: str = TOKEN, *, auth_date: int | None = None, user: dict | None = None) -> str:
    user = user or {"id": 42, "first_name": "Test", "username": "t"}
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAA",
        "user": json.dumps(user, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_init_data_parses_user():
    data = validate_init_data(build_init_data(), bot_token=TOKEN)
    assert data["user"]["id"] == 42


def test_tampered_hash_rejected():
    raw = build_init_data()
    tampered = raw.replace("Test", "Evil")
    with pytest.raises(AuthError):
        validate_init_data(tampered, bot_token=TOKEN)


def test_wrong_token_rejected():
    with pytest.raises(AuthError):
        validate_init_data(build_init_data(token="999:OTHER"), bot_token=TOKEN)


def test_expired_init_data_rejected():
    old = build_init_data(auth_date=int(time.time()) - 10_000)
    with pytest.raises(AuthError):
        validate_init_data(old, bot_token=TOKEN, max_age=3600)


def test_missing_hash_rejected():
    with pytest.raises(AuthError):
        validate_init_data("auth_date=1&user=%7B%7D", bot_token=TOKEN)
