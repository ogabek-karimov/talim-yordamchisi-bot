from datetime import datetime, timedelta, timezone

from app.db import session_scope
from app.models import Status
from app.services import subscriptions as subs_svc
from app.services import users as users_svc
from tests.conftest import auth_header


async def test_gate_open_when_feature_disabled(client, make_user):
    await make_user(700001, status=Status.APPROVED)
    async with session_scope() as s:
        assert await subs_svc.is_enabled(s) is False
    # submitting requires SubscribedUser; with feature off it should not 402
    r = await client.get("/api/student/subjects", headers=auth_header(700001))
    assert r.status_code == 200


async def test_gate_closes_when_enabled_and_no_sub(client, make_user):
    await make_user(700002, role="admin", status=Status.APPROVED)
    # enable via admin API
    r = await client.put(
        "/api/admin/subscription", json={"enabled": True}, headers=auth_header(700002)
    )
    assert r.status_code == 200 and r.json()["enabled"] is True

    await make_user(700003, status=Status.APPROVED)
    # AI endpoint is gated by SubscribedUser
    r = await client.post(
        "/api/ai/explain",
        json={"body": "x", "options": ["a", "b"], "correct_index": 0},
        headers=auth_header(700003),
    )
    assert r.status_code == 402


async def test_extend_is_idempotent_by_charge_id():
    async with session_scope() as s:
        user, _ = await users_svc.get_or_create(s, 700004, first_name="S")
        user.status = Status.APPROVED
        await s.flush()

        await subs_svc.extend(s, user, days=30, plan_key="m1", stars=150, charge_id="CH-1")
        first = user.subscription_until
        assert first is not None and first > datetime.now(timezone.utc) + timedelta(days=29)

        await subs_svc.extend(s, user, days=30, plan_key="m1", stars=150, charge_id="CH-1")
        assert user.subscription_until == first  # no double credit

        await subs_svc.extend(s, user, days=30, plan_key="m1", stars=150, charge_id="CH-2")
        assert user.subscription_until > first
