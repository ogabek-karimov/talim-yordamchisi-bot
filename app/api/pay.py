"""Mini App payment: list plans, create a Telegram Stars invoice link."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import ApprovedUser, SessionDep
from app.bot.handlers.payments import PAYLOAD_PREFIX
from app.bot.instance import get_bot
from app.i18n import t
from app.services import subscriptions as subs_svc
from app.services.testbank import pick

router = APIRouter(prefix="/api/pay", tags=["pay"])


class InvoiceIn(BaseModel):
    plan_key: str


@router.get("/plans")
async def plans(user: ApprovedUser, session: SessionDep) -> dict:
    enabled = await subs_svc.is_enabled(session)
    raw = await subs_svc.plans(session)
    return {
        "enabled": enabled,
        "plans": [
            {
                "key": p["key"],
                "days": p["days"],
                "stars": p["stars"],
                "title": pick(p.get("title_i18n"), user.language) or p["key"],
            }
            for p in raw
        ],
    }


@router.post("/invoice")
async def invoice(body: InvoiceIn, user: ApprovedUser, session: SessionDep) -> dict:
    if not await subs_svc.is_enabled(session):
        raise HTTPException(status.HTTP_409_CONFLICT, "subscription feature disabled")
    plan = await subs_svc.get_plan(session, body.plan_key)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown plan")
    bot = get_bot()
    if bot is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "bot unavailable")

    from aiogram.types import LabeledPrice

    title = pick(plan.get("title_i18n"), user.language) or plan["key"]
    link = await bot.create_invoice_link(
        title=t("app.sub.extend", user.language),
        description=t("sub.plan_line", user.language, title=title, days=plan["days"], stars=plan["stars"]),
        payload=f"{PAYLOAD_PREFIX}{plan['key']}",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=int(plan["stars"]))],
    )
    return {"link": link}
