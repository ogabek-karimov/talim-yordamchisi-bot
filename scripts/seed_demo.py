"""Populate a small demo test bank (idempotent).

Usage:  python -m scripts.seed_demo
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import init_models, session_scope
from app.models import Question, Subject, TestSet

DEMO = [
    {
        "slug": "math",
        "name_i18n": {"uz": "Matematika", "ru": "Математика", "en": "Mathematics", "kaa": "Matematika"},
        "sets": [
            {
                "title_i18n": {"uz": "Arifmetika — 1", "ru": "Арифметика — 1", "en": "Arithmetic — 1", "kaa": "Arifmetika — 1"},
                "time_limit_sec": 300,
                "questions": [
                    {
                        "body_i18n": {"uz": "2 + 2 × 2 = ?", "ru": "2 + 2 × 2 = ?", "en": "2 + 2 × 2 = ?", "kaa": "2 + 2 × 2 = ?"},
                        "options_i18n": {
                            "uz": ["6", "8", "4", "10"], "ru": ["6", "8", "4", "10"],
                            "en": ["6", "8", "4", "10"], "kaa": ["6", "8", "4", "10"],
                        },
                        "correct_index": 0,
                        "explanation_i18n": {
                            "uz": "Ko‘paytirish avval bajariladi: 2 × 2 = 4, keyin 2 + 4 = 6.",
                            "ru": "Сначала умножение: 2 × 2 = 4, затем 2 + 4 = 6.",
                            "en": "Multiplication first: 2 × 2 = 4, then 2 + 4 = 6.",
                            "kaa": "Aldın kóbeytiw: 2 × 2 = 4, keyin 2 + 4 = 6.",
                        },
                    },
                    {
                        "body_i18n": {
                            "uz": "15% ning 200 dan qiymati nechaga teng?",
                            "ru": "Сколько составляет 15% от 200?",
                            "en": "What is 15% of 200?",
                            "kaa": "200 dıń 15% i qansha?",
                        },
                        "options_i18n": {
                            "uz": ["30", "15", "45", "20"], "ru": ["30", "15", "45", "20"],
                            "en": ["30", "15", "45", "20"], "kaa": ["30", "15", "45", "20"],
                        },
                        "correct_index": 0,
                        "explanation_i18n": {
                            "uz": "200 × 15 / 100 = 30.",
                            "ru": "200 × 15 / 100 = 30.",
                            "en": "200 × 15 / 100 = 30.",
                            "kaa": "200 × 15 / 100 = 30.",
                        },
                    },
                ],
            }
        ],
    },
    {
        "slug": "english",
        "name_i18n": {"uz": "Ingliz tili", "ru": "Английский язык", "en": "English", "kaa": "Inglis tili"},
        "sets": [
            {
                "title_i18n": {"uz": "Grammatika — 1", "ru": "Грамматика — 1", "en": "Grammar — 1", "kaa": "Grammatika — 1"},
                "time_limit_sec": 240,
                "questions": [
                    {
                        "body_i18n": {
                            "uz": "She ___ to school every day.",
                            "ru": "She ___ to school every day.",
                            "en": "She ___ to school every day.",
                            "kaa": "She ___ to school every day.",
                        },
                        "options_i18n": {
                            "uz": ["goes", "go", "going", "gone"], "ru": ["goes", "go", "going", "gone"],
                            "en": ["goes", "go", "going", "gone"], "kaa": ["goes", "go", "going", "gone"],
                        },
                        "correct_index": 0,
                        "explanation_i18n": {
                            "uz": "3-shaxs birlikda Present Simple: fe’lga -es qo‘shiladi → goes.",
                            "ru": "Present Simple, 3-е лицо ед. ч.: добавляется -es → goes.",
                            "en": "Present Simple, third person singular takes -es → goes.",
                            "kaa": "Present Simple, 3-shaxs birlik: -es qosıladı → goes.",
                        },
                    }
                ],
            }
        ],
    },
]


async def run() -> None:
    await init_models()
    async with session_scope() as session:
        for subj in DEMO:
            existing = (
                await session.execute(select(Subject).where(Subject.slug == subj["slug"]))
            ).scalar_one_or_none()
            if existing:
                print(f"subject {subj['slug']} exists, skipping")
                continue
            subject = Subject(slug=subj["slug"], name_i18n=subj["name_i18n"], active=True)
            session.add(subject)
            await session.flush()
            for s in subj["sets"]:
                ts = TestSet(
                    subject_id=subject.id,
                    title_i18n=s["title_i18n"],
                    description_i18n={},
                    time_limit_sec=s["time_limit_sec"],
                    active=True,
                )
                session.add(ts)
                await session.flush()
                for i, q in enumerate(s["questions"]):
                    session.add(
                        Question(
                            test_set_id=ts.id,
                            order=i,
                            body_i18n=q["body_i18n"],
                            options_i18n=q["options_i18n"],
                            correct_index=q["correct_index"],
                            explanation_i18n=q["explanation_i18n"],
                        )
                    )
            print(f"seeded subject {subj['slug']}")
    print("done.")


if __name__ == "__main__":
    asyncio.run(run())
