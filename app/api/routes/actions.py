from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.services.gmail import modify_thread_labels, GmailError

# NOTE: this is already in your repo and is the correct place to fetch/refresh tokens
from app.services.gmail_sync import _get_access_token  # uses GmailToken table + refresh flow

router = APIRouter(prefix="/actions", tags=["actions"])


class ThreadLabelModifyIn(BaseModel):
    user_id: uuid.UUID
    thread_id: str = Field(..., min_length=3)
    add_label_ids: list[str] = Field(default_factory=list)
    remove_label_ids: list[str] = Field(default_factory=list)


@router.post("/thread/labels")
async def apply_thread_labels(req: ThreadLabelModifyIn, session: AsyncSession = Depends(get_session)) -> dict:
    """
    Calls Gmail threads.modify for a thread_id, using the user's DB token store.
    """
    access_token = await _get_access_token(session=session, user_id=req.user_id)
    if not access_token:
        raise HTTPException(status_code=401, detail="Missing Gmail token for this user_id.")

    try:
        out = await modify_thread_labels(
            access_token=access_token,
            thread_id=req.thread_id,
            add_label_ids=req.add_label_ids,
            remove_label_ids=req.remove_label_ids,
        )
        return {"ok": True, "gmail": out}
    except GmailError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
