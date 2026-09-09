"""Send a message to every approved user (best-effort, rate-limited)."""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import users as users_svc
from app.services.notifications import dm


async def broadcast(session: AsyncSession, text: str, *, batch: int = 25, pause: float = 1.0) -> tuple[int, int]:
    ids = await users_svc.approved_ids(session)
    ok = 0
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        results = await asyncio.gather(*(dm(uid, text) for uid in chunk))
        ok += sum(1 for r in results if r)
        if i + batch < len(ids):
            await asyncio.sleep(pause)
    return ok, len(ids)
