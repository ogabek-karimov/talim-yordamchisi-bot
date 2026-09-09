"""Admin panel API. Every route requires staff; some require the owner."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import OwnerUser, SessionDep, StaffUser
from app.api.presenters import application_dto, user_dto
from app.i18n import t
from app.models import Role
from app.services import applications as apps_svc
from app.services import audit as audit_svc
from app.services import broadcast as broadcast_svc
from app.services import subscriptions as subs_svc
from app.services import testbank
from app.services import users as users_svc
from app.services.notifications import dm

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- overview ---------------------------------------------------
@router.get("/overview")
async def overview(_: StaffUser, session: SessionDep) -> dict:
    return {
        "counts": await users_svc.counts(session),
        "subscription_enabled": await subs_svc.is_enabled(session),
        "audit": [
            {
                "action": a.action,
                "actor": a.actor_tg_id,
                "target": a.target,
                "at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in await audit_svc.recent(session, 20)
        ],
    }


# --- applications --------------------------------------------
@router.get("/applications")
async def list_applications(_: StaffUser, session: SessionDep) -> list[dict]:
    return [application_dto(a) for a in await apps_svc.list_pending(session)]


@router.post("/applications/{app_id}/approve")
async def approve_application(app_id: int, staff: StaffUser, session: SessionDep) -> dict:
    app = await apps_svc.approve(session, app_id, by=staff.tg_id)
    if app is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "already decided")
    await dm(app.tg_id, t("notify.approved", app.language))
    return {"ok": True}


class RejectIn(BaseModel):
    reason: str | None = None


@router.post("/applications/{app_id}/reject")
async def reject_application(app_id: int, body: RejectIn, staff: StaffUser, session: SessionDep) -> dict:
    app = await apps_svc.reject(session, app_id, by=staff.tg_id, reason=body.reason)
    if app is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "already decided")
    text = (
        t("notify.rejected", app.language, reason=body.reason)
        if body.reason
        else t("notify.rejected_no_reason", app.language)
    )
    await dm(app.tg_id, text)
    return {"ok": True}


# --- users --------------------------------------------------
@router.get("/users")
async def list_users(
    _: StaffUser,
    session: SessionDep,
    q: str | None = None,
    role: str | None = None,
    status_: str | None = Query(None, alias="status"),
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    rows = await users_svc.list_users(
        session,
        roles=[role] if role else None,
        statuses=[status_] if status_ else None,
        query=q,
        limit=min(limit, 200),
        offset=offset,
    )
    return [user_dto(u) for u in rows]


class AddUserIn(BaseModel):
    tg_id: int
    name: str | None = None


@router.post("/users")
async def add_user(body: AddUserIn, staff: StaffUser, session: SessionDep) -> dict:
    user, already = await users_svc.add_manual(session, body.tg_id, by=staff.tg_id, name=body.name)
    if not already:
        await dm(body.tg_id, t("notify.added_by_admin", user.language))
    return {"ok": True, "already": already, "user": user_dto(user)}


@router.post("/users/{tg_id}/block")
async def block_user(tg_id: int, staff: StaffUser, session: SessionDep) -> dict:
    user = await users_svc.block(session, tg_id, by=staff.tg_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    await dm(tg_id, t("notify.blocked", user.language))
    return {"ok": True}


@router.post("/users/{tg_id}/unblock")
async def unblock_user(tg_id: int, staff: StaffUser, session: SessionDep) -> dict:
    user = await users_svc.unblock(session, tg_id, by=staff.tg_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    await dm(tg_id, t("notify.unblocked", user.language))
    return {"ok": True}


@router.post("/users/{tg_id}/remove")
async def remove_user(tg_id: int, staff: StaffUser, session: SessionDep) -> dict:
    user = await users_svc.remove(session, tg_id, by=staff.tg_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return {"ok": True}


# --- admins / ownership (owner only) --------------------
@router.get("/admins")
async def list_admins(_: StaffUser, session: SessionDep) -> list[dict]:
    rows = await users_svc.list_users(session, roles=[Role.OWNER, Role.ADMIN], limit=200)
    return [user_dto(u) for u in rows]


class TgIdIn(BaseModel):
    tg_id: int


@router.post("/admins")
async def add_admin(body: TgIdIn, owner: OwnerUser, session: SessionDep) -> dict:
    user = await users_svc.make_admin(session, body.tg_id, by=owner.tg_id)
    await dm(body.tg_id, t("notify.role_promoted_admin", user.language))
    return {"ok": True, "user": user_dto(user)}


@router.delete("/admins/{tg_id}")
async def remove_admin(tg_id: int, owner: OwnerUser, session: SessionDep) -> dict:
    user = await users_svc.remove_admin(session, tg_id, by=owner.tg_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "admin not found")
    await dm(tg_id, t("notify.role_demoted", user.language))
    return {"ok": True}


@router.post("/transfer-ownership")
async def transfer_ownership(body: TgIdIn, owner: OwnerUser, session: SessionDep) -> dict:
    try:
        new_owner = await users_svc.transfer_ownership(session, body.tg_id, by=owner.tg_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await dm(body.tg_id, t("notify.ownership_received", new_owner.language))
    return {"ok": True}


# --- subscription ----------------------------------------
class SubscriptionIn(BaseModel):
    enabled: bool | None = None
    plans: list[dict] | None = None


@router.get("/subscription")
async def get_subscription(_: StaffUser, session: SessionDep) -> dict:
    return {
        "enabled": await subs_svc.is_enabled(session),
        "plans": await subs_svc.plans(session),
    }


@router.put("/subscription")
async def update_subscription(body: SubscriptionIn, staff: StaffUser, session: SessionDep) -> dict:
    if body.enabled is not None:
        await subs_svc.set_enabled(session, body.enabled, by=staff.tg_id)
    if body.plans is not None:
        await subs_svc.set_plans(session, body.plans, by=staff.tg_id)
    return {
        "enabled": await subs_svc.is_enabled(session),
        "plans": await subs_svc.plans(session),
    }


# --- content (test bank) --------------------------------
class SubjectIn(BaseModel):
    slug: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    active: bool = True
    order: int = 0


class SetIn(BaseModel):
    subject_id: int | None = None
    title_i18n: dict[str, str] = Field(default_factory=dict)
    description_i18n: dict[str, str] = Field(default_factory=dict)
    time_limit_sec: int = 0
    active: bool = True
    order: int = 0


class QuestionIn(BaseModel):
    test_set_id: int | None = None
    order: int = 0
    body_i18n: dict[str, str] = Field(default_factory=dict)
    options_i18n: dict[str, list[str]] = Field(default_factory=dict)
    correct_index: int = 0
    explanation_i18n: dict[str, str] = Field(default_factory=dict)
    image_url: str | None = None


def _subject_full(s) -> dict:
    return {"id": s.id, "slug": s.slug, "name_i18n": s.name_i18n, "active": s.active, "order": s.order}


def _set_full(x) -> dict:
    return {
        "id": x.id,
        "subject_id": x.subject_id,
        "title_i18n": x.title_i18n,
        "description_i18n": x.description_i18n,
        "time_limit_sec": x.time_limit_sec,
        "active": x.active,
        "order": x.order,
    }


def _question_full(q) -> dict:
    return {
        "id": q.id,
        "test_set_id": q.test_set_id,
        "order": q.order,
        "body_i18n": q.body_i18n,
        "options_i18n": q.options_i18n,
        "correct_index": q.correct_index,
        "explanation_i18n": q.explanation_i18n,
        "image_url": q.image_url,
    }


@router.get("/content/subjects")
async def content_subjects(_: StaffUser, session: SessionDep) -> list[dict]:
    return [_subject_full(s) for s in await testbank.list_subjects(session, only_active=False)]


@router.post("/content/subjects")
async def content_create_subject(body: SubjectIn, _: StaffUser, session: SessionDep) -> dict:
    s = await testbank.create_subject(
        session, slug=body.slug, name_i18n=body.name_i18n, order=body.order
    )
    return _subject_full(s)


@router.put("/content/subjects/{subject_id}")
async def content_update_subject(subject_id: int, body: SubjectIn, _: StaffUser, session: SessionDep) -> dict:
    s = await testbank.update_subject(
        session, subject_id, slug=body.slug, name_i18n=body.name_i18n, active=body.active, order=body.order
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "subject not found")
    return _subject_full(s)


@router.delete("/content/subjects/{subject_id}")
async def content_delete_subject(subject_id: int, _: StaffUser, session: SessionDep) -> dict:
    if not await testbank.delete_subject(session, subject_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "subject not found")
    return {"ok": True}


@router.get("/content/subjects/{subject_id}/sets")
async def content_sets(subject_id: int, _: StaffUser, session: SessionDep) -> list[dict]:
    rows = await testbank.list_sets(session, subject_id, only_active=False)
    counts = await testbank.question_counts(session, [r.id for r in rows])
    return [{**_set_full(r), "question_count": counts.get(r.id, 0)} for r in rows]


@router.post("/content/sets")
async def content_create_set(body: SetIn, staff: StaffUser, session: SessionDep) -> dict:
    if not body.subject_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "subject_id required")
    x = await testbank.create_set(
        session,
        subject_id=body.subject_id,
        title_i18n=body.title_i18n,
        description_i18n=body.description_i18n,
        time_limit_sec=body.time_limit_sec,
        active=body.active,
        order=body.order,
        created_by=staff.tg_id,
    )
    return _set_full(x)


@router.put("/content/sets/{set_id}")
async def content_update_set(set_id: int, body: SetIn, _: StaffUser, session: SessionDep) -> dict:
    x = await testbank.update_set(
        session,
        set_id,
        title_i18n=body.title_i18n,
        description_i18n=body.description_i18n,
        time_limit_sec=body.time_limit_sec,
        active=body.active,
        order=body.order,
    )
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "set not found")
    return _set_full(x)


@router.delete("/content/sets/{set_id}")
async def content_delete_set(set_id: int, _: StaffUser, session: SessionDep) -> dict:
    if not await testbank.delete_set(session, set_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "set not found")
    return {"ok": True}


@router.get("/content/sets/{set_id}/questions")
async def content_questions(set_id: int, _: StaffUser, session: SessionDep) -> list[dict]:
    ts = await testbank.get_set_with_questions(session, set_id)
    if ts is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "set not found")
    return [_question_full(q) for q in sorted(ts.questions, key=lambda x: x.order)]


@router.post("/content/questions")
async def content_create_question(body: QuestionIn, _: StaffUser, session: SessionDep) -> dict:
    if not body.test_set_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "test_set_id required")
    q = await testbank.create_question(
        session,
        test_set_id=body.test_set_id,
        order=body.order,
        body_i18n=body.body_i18n,
        options_i18n=body.options_i18n,
        correct_index=body.correct_index,
        explanation_i18n=body.explanation_i18n,
        image_url=body.image_url,
    )
    return _question_full(q)


@router.put("/content/questions/{q_id}")
async def content_update_question(q_id: int, body: QuestionIn, _: StaffUser, session: SessionDep) -> dict:
    q = await testbank.update_question(
        session,
        q_id,
        order=body.order,
        body_i18n=body.body_i18n,
        options_i18n=body.options_i18n,
        correct_index=body.correct_index,
        explanation_i18n=body.explanation_i18n,
        image_url=body.image_url,
    )
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    return _question_full(q)


@router.delete("/content/questions/{q_id}")
async def content_delete_question(q_id: int, _: StaffUser, session: SessionDep) -> dict:
    if not await testbank.delete_question(session, q_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    return {"ok": True}


# --- broadcast ------------------------------------------
class BroadcastIn(BaseModel):
    text: str


@router.post("/broadcast")
async def broadcast(body: BroadcastIn, _: StaffUser, session: SessionDep) -> dict:
    if not body.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty text")
    ok, total = await broadcast_svc.broadcast(session, body.text.strip())
    return {"ok": ok, "total": total}
