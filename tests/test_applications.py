from app.db import session_scope
from app.models import Status
from app.services import applications as apps_svc
from app.services import users as users_svc
from tests.conftest import auth_header


async def test_application_approve_creates_approved_user(client, make_user):
    await make_user(600001, role="admin", status=Status.APPROVED)

    async with session_scope() as s:
        app = await apps_svc.create(
            s, tg_id=777001, username="cand", full_name="Candi Date", phone="+998900000000", language="uz"
        )
        app_id = app.id

    r = await client.get("/api/admin/applications", headers=auth_header(600001))
    assert r.status_code == 200
    assert any(a["id"] == app_id for a in r.json())

    r = await client.post(f"/api/admin/applications/{app_id}/approve", headers=auth_header(600001))
    assert r.status_code == 200

    async with session_scope() as s:
        u = await users_svc.get_by_tg(s, 777001)
        assert u is not None and u.status == Status.APPROVED and u.role == "user"

    # second approve -> conflict
    r = await client.post(f"/api/admin/applications/{app_id}/approve", headers=auth_header(600001))
    assert r.status_code == 409


async def test_application_reject_keeps_user_pending(client, make_user):
    await make_user(600002, role="admin", status=Status.APPROVED)
    async with session_scope() as s:
        app = await apps_svc.create(
            s, tg_id=777002, username=None, full_name="No One", phone="+998911111111", language="ru"
        )
        app_id = app.id

    r = await client.post(
        f"/api/admin/applications/{app_id}/reject",
        json={"reason": "incomplete"},
        headers=auth_header(600002),
    )
    assert r.status_code == 200

    async with session_scope() as s:
        u = await users_svc.get_by_tg(s, 777002)
        assert u is None or u.status != Status.APPROVED
