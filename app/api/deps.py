"""FastAPI dependencies: auth, role gates, subscription gate."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Role, Status, User
from app.security import AuthError, verify_session
from app.services import subscriptions as subs_svc
from app.services import users as users_svc

SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = verify_session(token)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = await users_svc.get_by_tg(session, int(payload["uid"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_approved(user: CurrentUser) -> User:
    if user.status == Status.BLOCKED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "blocked")
    if not user.is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not approved")
    return user


ApprovedUser = Annotated[User, Depends(require_approved)]


async def require_staff(user: CurrentUser) -> User:
    if not (user.is_staff and user.is_approved):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "staff only")
    return user


StaffUser = Annotated[User, Depends(require_staff)]


async def require_owner(user: CurrentUser) -> User:
    if user.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    return user


OwnerUser = Annotated[User, Depends(require_owner)]


async def subscription_gate(user: ApprovedUser, session: SessionDep) -> User:
    if not await subs_svc.has_access(session, user):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "subscription required")
    return user


SubscribedUser = Annotated[User, Depends(subscription_gate)]
