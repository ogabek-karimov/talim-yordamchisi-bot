"""AI endpoints: homework helper + test explanation."""
from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import SessionDep, SubscribedUser
from app.config import settings
from app.i18n import t
from app.services import ai_service

router = APIRouter(prefix="/api/ai", tags=["ai"])

_ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp"}


@router.get("/status")
async def status_(_: SubscribedUser) -> dict:
    return {"enabled": ai_service.available()}


class ExplainIn(BaseModel):
    body: str
    options: list[str]
    correct_index: int
    chosen_index: int | None = None
    subject: str | None = None


@router.post("/homework")
async def homework(
    user: SubscribedUser,
    session: SessionDep,
    message: str = Form(""),
    history: str = Form("[]"),
    image: UploadFile | None = File(None),
) -> dict:
    if not ai_service.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, t("app.hw.disabled", user.language))
    if not message.strip() and image is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty request")
    if not await ai_service.within_rate_limit(session, user):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, t("app.hw.rate_limited", user.language))

    img_tuple = None
    if image is not None:
        raw = await image.read()
        if len(raw) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, t("app.hw.image_too_big", user.language))
        mime = image.content_type or "image/jpeg"
        if mime not in _ALLOWED_IMAGE:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported image type")
        img_tuple = (raw, mime)

    try:
        parsed_history = json.loads(history or "[]")
        parsed_history = [
            {"role": h["role"], "content": str(h["content"])[:4000]}
            for h in parsed_history
            if isinstance(h, dict) and h.get("role") in ("user", "assistant")
        ][-8:]
    except (json.JSONDecodeError, KeyError, TypeError):
        parsed_history = []

    try:
        reply = await ai_service.complete(
            system=ai_service.build_system_prompt(user.language, "homework"),
            user_text=message.strip()[:6000],
            history=parsed_history,
            image=img_tuple,
        )
    except ai_service.AIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    await ai_service.record_usage(session, user, "homework")
    return {"reply": reply}


@router.post("/explain")
async def explain(body: ExplainIn, user: SubscribedUser, session: SessionDep) -> dict:
    if not ai_service.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, t("app.hw.disabled", user.language))
    if not await ai_service.within_rate_limit(session, user):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, t("app.hw.rate_limited", user.language))

    opts = "\n".join(f"{i + 1}. {o}" for i, o in enumerate(body.options))
    chosen = (
        f"The student chose option {body.chosen_index + 1}."
        if body.chosen_index is not None and 0 <= body.chosen_index < len(body.options)
        else "The student did not answer."
    )
    prompt = (
        f"Question: {body.body}\n\nOptions:\n{opts}\n\n"
        f"Correct option: {body.correct_index + 1}\n{chosen}\n\n"
        "Explain the correct answer."
    )
    try:
        reply = await ai_service.complete(
            system=ai_service.build_system_prompt(user.language, "explain"),
            user_text=prompt,
        )
    except ai_service.AIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    await ai_service.record_usage(session, user, "explain")
    return {"reply": reply}
