import pytest

from app.db import session_scope
from app.models import Role, Status
from app.services import users as users_svc
from tests.conftest import auth_header


async def test_transfer_ownership_swaps_roles(client, make_user):
    # seeded owner is 500000
    await make_user(800001, role=Role.ADMIN, status=Status.APPROVED)

    r = await client.post(
        "/api/admin/transfer-ownership",
        json={"tg_id": 800001},
        headers=auth_header(500000),
    )
    assert r.status_code == 200, r.text

    async with session_scope() as s:
        old = await users_svc.get_by_tg(s, 500000)
        new = await users_svc.get_by_tg(s, 800001)
        assert new.role == Role.OWNER
        assert old.role == Role.ADMIN

    # the demoted owner can no longer transfer
    r = await client.post(
        "/api/admin/transfer-ownership",
        json={"tg_id": 500000},
        headers=auth_header(500000),
    )
    assert r.status_code == 403


async def test_transfer_to_non_admin_rejected():
    async with session_scope() as s:
        await users_svc.get_or_create(s, 800002, first_name="Plain")
        with pytest.raises(ValueError):
            await users_svc.transfer_ownership(s, 800002, by=500000)


async def test_only_one_owner_after_transfer(client, make_user):
    await make_user(800003, role=Role.ADMIN, status=Status.APPROVED)
    await client.post(
        "/api/admin/transfer-ownership", json={"tg_id": 800003}, headers=auth_header(500000)
    )
    async with session_scope() as s:
        owners = [u for u in await users_svc.list_users(s, roles=[Role.OWNER], limit=100)]
        assert len(owners) == 1 and owners[0].tg_id == 800003
