from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models import (
    ActionType,
    Message,
    MessageStatus,
    SuggestedAction,
    SuggestionStatus,
)

# (Existing Gmail endpoint deps — keep)
from app.services.gmail import GmailError, modify_thread_labels
from app.services.gmail_sync import _get_access_token  # uses GmailToken table + refresh flow

router = APIRouter(prefix="/actions", tags=["actions"])


# -----------------------------
# Existing Gmail endpoint (keep)
# -----------------------------
class ThreadLabelModifyIn(BaseModel):
    user_id: uuid.UUID
    thread_id: str = Field(..., min_length=3)
    add_label_ids: list[str] = Field(default_factory=list)
    remove_label_ids: list[str] = Field(default_factory=list)


@router.post("/thread/labels")
async def apply_thread_labels(
    req: ThreadLabelModifyIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """
    Calls Gmail threads.modify for a thread_id, using the user's DB token store.
    """
    access_token = await _get_access_token(session=session, user_id=req.user_id)
    if not access_token:
        raise HTTPException(
            status_code=401, detail="Missing Gmail token for this user_id."
        )

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


# -----------------------------
# Day 9: DB-only apply endpoint
# -----------------------------
Decision = Literal["accept", "reject"]


class ApplySuggestedActionIn(BaseModel):
    user_id: uuid.UUID
    suggested_action_id: uuid.UUID
    decision: Decision


class ApplySuggestedActionOut(BaseModel):
    ok: bool
    suggested_action_id: uuid.UUID
    decision: Decision
    previous_status: str
    new_status: str
    messages_updated: int
    message_status_set_to: str | None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_list_of_str(v: Any) -> list[str]:
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out
    return []


@router.post("/apply", response_model=ApplySuggestedActionOut)
async def apply_suggested_action(
    req: ApplySuggestedActionIn, session: AsyncSession = Depends(get_session)
) -> ApplySuggestedActionOut:
    # 1) Load suggested action
    sa = await session.scalar(
        select(SuggestedAction).where(
            SuggestedAction.id == req.suggested_action_id,
            SuggestedAction.user_id == req.user_id,
        )
    )
    if sa is None:
        raise HTTPException(
            status_code=404, detail="SuggestedAction not found for this user_id."
        )

    prev = sa.status

    # 2) Only allow decision once (no flipping accepted<->rejected)
    if sa.status != SuggestionStatus.proposed:
        raise HTTPException(
            status_code=409,
            detail=f"SuggestedAction already decided (status={sa.status.value}).",
        )

    # 3) Apply decision to SuggestedAction
    if req.decision == "accept":
        sa.status = SuggestionStatus.accepted
    else:
        sa.status = SuggestionStatus.rejected

    sa.decided_at = _now_utc()

    # 4) DB-only “apply”: update Message.status for supported action types (only on accept)
    messages_updated = 0
    status_set_to: MessageStatus | None = None

    if req.decision == "accept":
        if sa.action_type == ActionType.archive_all:
            status_set_to = MessageStatus.archived

        elif sa.action_type == ActionType.snooze:
            status_set_to = MessageStatus.snoozed

        elif sa.action_type == ActionType.label_remove:
            # If the rule is "remove INBOX", treat as "archive" for DB-only MVP
            remove_ids: list[str] = []
            if isinstance(sa.payload, dict):
                v = sa.payload.get("remove_label_ids")
                if isinstance(v, list):
                    remove_ids = [str(x).upper() for x in v if str(x).strip()]
            if "INBOX" in remove_ids:
                status_set_to = MessageStatus.archived
            else:
                status_set_to = None

        else:
            status_set_to = None

        if status_set_to is not None:
            res = await session.execute(
                update(Message)
                .where(
                    Message.user_id == req.user_id,
                    Message.cluster_id == sa.cluster_id,
                    Message.status == MessageStatus.inbox,  # only affect inbox
                )
                .values(status=status_set_to)
                .execution_options(synchronize_session=False)
            )
            messages_updated = int(res.rowcount or 0)

    await session.commit()

    return ApplySuggestedActionOut(
        ok=True,
        suggested_action_id=sa.id,
        decision=req.decision,
        previous_status=prev.value,
        new_status=sa.status.value,
        messages_updated=messages_updated,
        message_status_set_to=status_set_to.value if status_set_to is not None else None,
    )
