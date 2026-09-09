from app.db import session_scope
from app.models import Status
from app.services import testbank
from app.services import users as users_svc
from tests.conftest import auth_header


async def _seed_set():
    async with session_scope() as s:
        subject = await testbank.create_subject(
            s, slug="algebra", name_i18n={"uz": "Algebra", "ru": "Алгебра", "en": "Algebra", "kaa": "Algebra"}
        )
        ts = await testbank.create_set(s, subject_id=subject.id, title_i18n={"uz": "T1"}, time_limit_sec=0)
        q1 = await testbank.create_question(
            s,
            test_set_id=ts.id,
            body_i18n={"uz": "2+2?"},
            options_i18n={"uz": ["3", "4", "5"]},
            correct_index=1,
            explanation_i18n={"uz": "4"},
        )
        q2 = await testbank.create_question(
            s,
            test_set_id=ts.id,
            body_i18n={"uz": "3*3?"},
            options_i18n={"uz": ["6", "9", "12"]},
            correct_index=1,
            explanation_i18n={"uz": "9"},
        )
        return ts.id, q1.id, q2.id


async def test_grade_scores_and_reviews():
    set_id, q1, q2 = await _seed_set()
    async with session_scope() as s:
        user, _ = await users_svc.get_or_create(s, 900001, first_name="G")
        user.status = Status.APPROVED
        await s.flush()
        res = await testbank.grade(s, user=user, set_id=set_id, answers={str(q1): 1, str(q2): 0})
    assert res["score"] == 1
    assert res["total"] == 2
    wrong = [r for r in res["review"] if not r["is_correct"]]
    assert len(wrong) == 1 and wrong[0]["question_id"] == q2
    assert wrong[0]["correct_index"] == 1


async def test_student_set_endpoint_strips_answers(client, make_user):
    set_id, _, _ = await _seed_set()
    await make_user(900002, status=Status.APPROVED)
    r = await client.get(f"/api/student/sets/{set_id}", headers=auth_header(900002))
    assert r.status_code == 200
    payload = r.json()
    assert payload["questions"]
    for q in payload["questions"]:
        assert "correct_index" not in q
        assert "explanation" not in q


async def test_student_sets_list_hides_empty_sets(client, make_user):
    async with session_scope() as s:
        subject = await testbank.create_subject(s, slug="empty", name_i18n={"uz": "Empty"})
        await testbank.create_set(s, subject_id=subject.id, title_i18n={"uz": "no qs"})
        subject_id = subject.id
    await make_user(900003, status=Status.APPROVED)
    r = await client.get(f"/api/student/subjects/{subject_id}/sets", headers=auth_header(900003))
    assert r.status_code == 200
    assert r.json() == []
