import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.config import settings
from app.models import Role, Status
from tests.conftest import auth_header


def signed_init_data(user: dict) -> str:
    token = settings.bot_token  # "" in tests
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(user, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


async def test_auth_issues_token_and_me(client):
    init = signed_init_data({"id": 1001, "first_name": "Aa", "username": "aa", "language_code": "ru"})
    r = await client.post("/api/auth", json={"init_data": init})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["me"]["tg_id"] == 1001
    assert body["me"]["language"] == "ru"
    assert body["me"]["role"] == "user"
    assert body["i18n"]["common.yes"] == "Да"

    r2 = await client.get("/api/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert r2.status_code == 200
    assert r2.json()["tg_id"] == 1001


async def test_auth_rejects_bad_init_data(client):
    r = await client.post("/api/auth", json={"init_data": "hash=deadbeef&user=%7B%7D"})
    assert r.status_code == 401


async def test_regular_user_blocked_from_admin_api(client, make_user):
    await make_user(2002, role=Role.USER, status=Status.APPROVED)
    r = await client.get("/api/admin/overview", headers=auth_header(2002))
    assert r.status_code == 403


async def test_pending_user_blocked_from_student_api(client, make_user):
    await make_user(2003, role=Role.USER, status=Status.PENDING)
    r = await client.get("/api/student/subjects", headers=auth_header(2003))
    assert r.status_code == 403


async def test_staff_can_reach_admin_api(client, make_user):
    await make_user(2004, role=Role.ADMIN, status=Status.APPROVED)
    r = await client.get("/api/admin/overview", headers=auth_header(2004))
    assert r.status_code == 200
    assert "counts" in r.json()


async def test_add_admin_is_owner_only(client, make_user):
    await make_user(2005, role=Role.ADMIN, status=Status.APPROVED)  # admin, not owner
    r = await client.post("/api/admin/admins", json={"tg_id": 9999}, headers=auth_header(2005))
    assert r.status_code == 403

    # the seeded owner (OWNER_ID=500000) can
    r2 = await client.post("/api/admin/admins", json={"tg_id": 9999}, headers=auth_header(500000))
    assert r2.status_code == 200
