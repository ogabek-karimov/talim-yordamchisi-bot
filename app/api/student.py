"""Student-facing endpoints: subjects, test sets, questions, attempts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import ApprovedUser, SessionDep, SubscribedUser
from app.i18n import SUPPORTED
from app.models import Attempt
from app.services import testbank
from app.services import users as users_svc

router = APIRouter(prefix="/api/student", tags=["student"])


class LangIn(BaseModel):
    language: str


class SubmitIn(BaseModel):
    answers: dict[str, int]


@router.post("/language")
async def set_language(body: LangIn, user: ApprovedUser, session: SessionDep) -> dict:
    if body.language not in SUPPORTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported language")
    await users_svc.set_language(session, user, body.language)
    return {"language": user.language}


@router.get("/subjects")
async def subjects(user: ApprovedUser, session: SessionDep) -> list[dict]:
    rows = await testbank.list_subjects(session)
    return [testbank.subject_dto(s, user.language) for s in rows]


@router.get("/subjects/{subject_id}/sets")
async def sets(subject_id: int, user: ApprovedUser, session: SessionDep) -> list[dict]:
    rows = await testbank.list_sets(session, subject_id)
    counts = await testbank.question_counts(session, [r.id for r in rows])
    return [
        testbank.set_dto(r, user.language, question_count=counts.get(r.id, 0))
        for r in rows
        if counts.get(r.id, 0) > 0
    ]


@router.get("/sets/{set_id}")
async def get_set(set_id: int, user: ApprovedUser, session: SessionDep) -> dict:
    ts = await testbank.get_set_with_questions(session, set_id)
    if ts is None or not ts.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test set not found")
    return {
        **testbank.set_dto(ts, user.language, question_count=len(ts.questions)),
        "questions": [
            testbank.question_dto(q, user.language, include_answer=False)
            for q in sorted(ts.questions, key=lambda x: x.order)
        ],
    }


@router.post("/sets/{set_id}/submit")
async def submit(set_id: int, body: SubmitIn, user: SubscribedUser, session: SessionDep) -> dict:
    try:
        return await testbank.grade(session, user=user, set_id=set_id, answers=body.answers)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/attempts")
async def attempts(user: ApprovedUser, session: SessionDep, limit: int = 20) -> list[dict]:
    rows = (
        await session.execute(
            select(Attempt)
            .where(Attempt.user_id == user.id)
            .order_by(Attempt.id.desc())
            .limit(min(limit, 100))
        )
    ).scalars().all()
    return [
        {
            "id": a.id,
            "test_set_id": a.test_set_id,
            "score": a.score,
            "total": a.total,
            "finished_at": a.finished_at.isoformat() if a.finished_at else None,
        }
        for a in rows
    ]
