"""Mini App authentication + bootstrap data."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.api.presenters import me_payload
from app.config import settings
from app.i18n import LANGUAGE_NAMES, SUPPORTED, catalog
from app.security import AuthError, issue_session, validate_init_data
from app.services import users as users_svc

router = APIRouter(prefix="/api", tags=["auth"])


class AuthIn(BaseModel):
    init_data: str


@router.post("/auth")
async def auth(body: AuthIn, session: SessionDep) -> dict:
    try:
        data = validate_init_data(body.init_data)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid initData: {exc}") from exc

    tg = data.get("user")
    if not isinstance(tg, dict) or "id" not in tg:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no user in initData")

    user, _ = await users_svc.get_or_create(
        session,
        int(tg["id"]),
        username=tg.get("username"),
        first_name=tg.get("first_name"),
        last_name=tg.get("last_name"),
        language=tg.get("language_code"),
    )
    token = issue_session(user.tg_id)
    return {
        "token": token,
        "me": await me_payload(session, user),
        "languages": [{"code": c, "name": LANGUAGE_NAMES[c]} for c in SUPPORTED],
        "i18n": catalog(user.language),
        "webapp_url": settings.webapp_url,
    }


@router.get("/me")
async def me(user: CurrentUser, session: SessionDep) -> dict:
    return await me_payload(session, user)


@router.get("/i18n/{lang}")
async def i18n(lang: str) -> dict:
    if lang not in SUPPORTED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown language")
    return catalog(lang)
