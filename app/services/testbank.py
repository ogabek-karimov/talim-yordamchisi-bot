"""Test bank: subjects, test sets, questions, attempts + grading."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.i18n import normalize_lang
from app.models import Attempt, Question, Subject, TestSet, User, utcnow


def pick(i18n: dict | None, lang: str) -> str:
    i18n = i18n or {}
    if not i18n:
        return ""
    lang = normalize_lang(lang)
    return i18n.get(lang) or i18n.get("uz") or next(iter(i18n.values()), "")


# --- read (student-facing) ------------------------------------------
async def list_subjects(session: AsyncSession, *, only_active: bool = True) -> list[Subject]:
    stmt = select(Subject).order_by(Subject.order, Subject.id)
    if only_active:
        stmt = stmt.where(Subject.active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def list_sets(
    session: AsyncSession, subject_id: int, *, only_active: bool = True
) -> list[TestSet]:
    stmt = (
        select(TestSet)
        .where(TestSet.subject_id == subject_id)
        .order_by(TestSet.order, TestSet.id)
    )
    if only_active:
        stmt = stmt.where(TestSet.active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def get_set_with_questions(session: AsyncSession, set_id: int) -> TestSet | None:
    return (
        await session.execute(
            select(TestSet)
            .where(TestSet.id == set_id)
            .options(selectinload(TestSet.questions))
        )
    ).scalar_one_or_none()


def subject_dto(subject: Subject, lang: str) -> dict:
    return {"id": subject.id, "slug": subject.slug, "name": pick(subject.name_i18n, lang)}


def set_dto(ts: TestSet, lang: str, *, question_count: int | None = None) -> dict:
    return {
        "id": ts.id,
        "subject_id": ts.subject_id,
        "title": pick(ts.title_i18n, lang),
        "description": pick(ts.description_i18n, lang),
        "time_limit_sec": ts.time_limit_sec,
        "question_count": question_count,
    }


def question_dto(q: Question, lang: str, *, include_answer: bool = False) -> dict:
    opts = (q.options_i18n or {}).get(normalize_lang(lang)) or (q.options_i18n or {}).get("uz") or []
    dto = {
        "id": q.id,
        "order": q.order,
        "body": pick(q.body_i18n, lang),
        "options": list(opts),
        "image_url": q.image_url,
    }
    if include_answer:
        dto["correct_index"] = q.correct_index
        dto["explanation"] = pick(q.explanation_i18n, lang)
    return dto


# --- grading -------------------------------------------------------
async def grade(
    session: AsyncSession,
    *,
    user: User,
    set_id: int,
    answers: dict[str, int],
) -> dict:
    ts = await get_set_with_questions(session, set_id)
    if ts is None:
        raise ValueError("test set not found")

    lang = user.language
    normalized = {str(k): int(v) for k, v in answers.items() if str(v).lstrip("-").isdigit()}
    score = 0
    review = []
    for q in ts.questions:
        chosen = normalized.get(str(q.id))
        correct = q.correct_index
        ok = chosen is not None and chosen == correct
        if ok:
            score += 1
        review.append(
            {
                "question_id": q.id,
                "body": pick(q.body_i18n, lang),
                "options": (q.options_i18n or {}).get(normalize_lang(lang))
                or (q.options_i18n or {}).get("uz")
                or [],
                "chosen_index": chosen,
                "correct_index": correct,
                "is_correct": ok,
                "explanation": pick(q.explanation_i18n, lang),
            }
        )

    attempt = Attempt(
        user_id=user.id,
        test_set_id=set_id,
        started_at=utcnow(),
        finished_at=utcnow(),
        score=score,
        total=len(ts.questions),
        answers=normalized,
    )
    session.add(attempt)
    await session.flush()
    return {
        "attempt_id": attempt.id,
        "score": score,
        "total": len(ts.questions),
        "review": review,
    }


# --- write (admin) ------------------------------------------------
async def create_subject(session: AsyncSession, *, slug: str, name_i18n: dict, order: int = 0) -> Subject:
    subject = Subject(slug=slug.strip().lower()[:64], name_i18n=name_i18n, order=order, active=True)
    session.add(subject)
    await session.flush()
    return subject


async def update_subject(session: AsyncSession, subject_id: int, **fields) -> Subject | None:
    subject = await session.get(Subject, subject_id)
    if subject is None:
        return None
    for key in ("slug", "name_i18n", "active", "order"):
        if key in fields and fields[key] is not None:
            setattr(subject, key, fields[key])
    await session.flush()
    return subject


async def delete_subject(session: AsyncSession, subject_id: int) -> bool:
    subject = await session.get(Subject, subject_id)
    if subject is None:
        return False
    await session.delete(subject)
    await session.flush()
    return True


async def create_set(session: AsyncSession, *, subject_id: int, title_i18n: dict, **fields) -> TestSet:
    ts = TestSet(
        subject_id=subject_id,
        title_i18n=title_i18n,
        description_i18n=fields.get("description_i18n") or {},
        time_limit_sec=int(fields.get("time_limit_sec") or 0),
        order=int(fields.get("order") or 0),
        active=bool(fields.get("active", True)),
        created_by=fields.get("created_by"),
    )
    session.add(ts)
    await session.flush()
    return ts


async def update_set(session: AsyncSession, set_id: int, **fields) -> TestSet | None:
    ts = await session.get(TestSet, set_id)
    if ts is None:
        return None
    for key in ("title_i18n", "description_i18n", "time_limit_sec", "order", "active"):
        if key in fields and fields[key] is not None:
            setattr(ts, key, fields[key])
    await session.flush()
    return ts


async def delete_set(session: AsyncSession, set_id: int) -> bool:
    ts = await session.get(TestSet, set_id)
    if ts is None:
        return False
    await session.delete(ts)
    await session.flush()
    return True


async def create_question(session: AsyncSession, *, test_set_id: int, **fields) -> Question:
    count = (
        await session.execute(
            select(func.count(Question.id)).where(Question.test_set_id == test_set_id)
        )
    ).scalar_one()
    q = Question(
        test_set_id=test_set_id,
        order=int(fields.get("order") or count),
        body_i18n=fields.get("body_i18n") or {},
        options_i18n=fields.get("options_i18n") or {},
        correct_index=int(fields.get("correct_index") or 0),
        explanation_i18n=fields.get("explanation_i18n") or {},
        image_url=fields.get("image_url"),
    )
    session.add(q)
    await session.flush()
    return q


async def update_question(session: AsyncSession, q_id: int, **fields) -> Question | None:
    q = await session.get(Question, q_id)
    if q is None:
        return None
    for key in ("order", "body_i18n", "options_i18n", "correct_index", "explanation_i18n", "image_url"):
        if key in fields and fields[key] is not None:
            setattr(q, key, fields[key])
    await session.flush()
    return q


async def delete_question(session: AsyncSession, q_id: int) -> bool:
    q = await session.get(Question, q_id)
    if q is None:
        return False
    await session.delete(q)
    await session.flush()
    return True


async def question_counts(session: AsyncSession, set_ids: list[int]) -> dict[int, int]:
    if not set_ids:
        return {}
    rows = await session.execute(
        select(Question.test_set_id, func.count(Question.id))
        .where(Question.test_set_id.in_(set_ids))
        .group_by(Question.test_set_id)
    )
    return {int(sid): int(c) for sid, c in rows.all()}
