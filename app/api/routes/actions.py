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

from app.services.gmail import (
    GmailError,
    modify_thread_labels,
    ensure_label_id,
)
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


# -----------------------------
# Day 12: Gmail + DB apply endpoint
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

    # DB outcome
    messages_updated: int
    message_status_set_to: str | None

    # Gmail outcome (Day 12)
    gmail_attempted: bool
    gmail_threads_targeted: int
    gmail_threads_changed: int
    gmail_error: str | None


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


async def _infer_thread_ids_for_cluster(
    session: AsyncSession, *, user_id: uuid.UUID, cluster_id: uuid.UUID
) -> list[str]:
    """
    If payload didn't provide thread_ids, infer from DB messages in the cluster.
    """
    rows = await session.execute(
        select(Message.thread_external_id).where(
            Message.user_id == user_id,
            Message.cluster_id == cluster_id,
        )
    )
    tids = sorted({t for (t,) in rows.all() if t})
    return tids


def _payload_dict(sa: SuggestedAction) -> dict[str, Any]:
    return sa.payload if isinstance(sa.payload, dict) else {}


def _upper_list(xs: list[str]) -> list[str]:
    return [x.strip().upper() for x in xs if isinstance(x, str) and x.strip()]


async def _apply_gmail_for_action(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    sa: SuggestedAction,
) -> tuple[bool, int, int, str | None]:
    """
    Returns:
      (attempted, targeted_threads, changed_threads, error_or_none)

    Rules:
      - If no gmail token -> attempted False
      - If no thread ids -> attempted False
      - For system label operations, Gmail expects label IDs like "INBOX", "TRASH", "SPAM", "SNOOZED" (if supported)
      - For label_add with label_name -> ensure label exists and use its ID
    """
    # Try to get token; if missing, we silently fallback to DB-only
    try:
        access_token = await _get_access_token(session=session, user_id=user_id)
    except Exception:
        return (False, 0, 0, None)

    payload = _payload_dict(sa)

    # thread_ids priority: payload.thread_ids else infer from DB cluster messages
    thread_ids = _as_list_of_str(payload.get("thread_ids"))
    if not thread_ids:
        thread_ids = await _infer_thread_ids_for_cluster(session, user_id=user_id, cluster_id=sa.cluster_id)

    if not thread_ids:
        return (False, 0, 0, None)

    # Determine Gmail label modifications
    add_ids: list[str] = []
    remove_ids: list[str] = []

    # Normalize incoming lists
    add_from_payload = _upper_list(_as_list_of_str(payload.get("add_label_ids")))
    remove_from_payload = _upper_list(_as_list_of_str(payload.get("remove_label_ids")))

    if sa.action_type == ActionType.archive_all:
        # Archive in Gmail = remove INBOX
        remove_ids = ["INBOX"]

    elif sa.action_type == ActionType.label_remove:
        # Directly use remove_label_ids (often ["INBOX"])
        remove_ids = remove_from_payload

    elif sa.action_type == ActionType.snooze:
        # Gmail has a system label "SNOOZED" for snoozed threads (commonly supported).
        # If the account/API doesn't support it, Gmail will error; we catch and surface.
        add_ids = ["SNOOZED"]

    elif sa.action_type == ActionType.label_add:
        # If payload provides add_label_ids, use them
        if add_from_payload:
            add_ids = add_from_payload
        else:
            # Or payload can provide label_name (from summarizer)
            label_name = str(payload.get("label_name") or "").strip()
            if label_name:
                # ensure_label_id returns Gmail label ID
                lid = await ensure_label_id(access_token=access_token, label_name=label_name)
                add_ids = [lid]
            else:
                # Nothing to do
                add_ids = []

    else:
        # reply_with_template not implemented for Gmail here
        return (False, len(thread_ids), 0, None)

    # If nothing to change, skip
    if not add_ids and not remove_ids:
        return (False, len(thread_ids), 0, None)

    # Apply to all threads (best-effort: fail fast on first error to keep consistency)
    changed = 0
    try:
        for tid in thread_ids:
            await modify_thread_labels(
                access_token=access_token,
                thread_id=tid,
                add_label_ids=add_ids,
                remove_label_ids=remove_ids,
            )
            changed += 1
    except GmailError as e:
        return (True, len(thread_ids), changed, str(e))

    return (True, len(thread_ids), changed, None)


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
        raise HTTPException(status_code=404, detail="SuggestedAction not found for this user_id.")

    prev = sa.status

    # 2) Only allow decision once (no flipping accepted<->rejected)
    if sa.status != SuggestionStatus.proposed:
        raise HTTPException(
            status_code=409,
            detail=f"SuggestedAction already decided (status={sa.status.value}).",
        )

    # 3) Apply decision (we only execute Gmail/DB changes on accept)
    if req.decision == "accept":
        sa.status = SuggestionStatus.accepted
    else:
        sa.status = SuggestionStatus.rejected

    sa.decided_at = _now_utc()

    # 4) Day 12: If accept, attempt Gmail first (so we can fail without committing DB)
    gmail_attempted = False
    gmail_threads_targeted = 0
    gmail_threads_changed = 0
    gmail_error: str | None = None

    if req.decision == "accept":
        gmail_attempted, gmail_threads_targeted, gmail_threads_changed, gmail_error = await _apply_gmail_for_action(
            session=session,
            user_id=req.user_id,
            sa=sa,
        )

        # If we tried Gmail and got an error, fail the request (no commit)
        # so status doesn't say "accepted" while Gmail didn't apply.
        if gmail_attempted and gmail_error:
            await session.rollback()
            raise HTTPException(status_code=502, detail=f"Gmail apply failed: {gmail_error}")

    # 5) DB apply: update Message.status for supported action types (only on accept)
    messages_updated = 0
    status_set_to: MessageStatus | None = None

    if req.decision == "accept":
        if sa.action_type == ActionType.archive_all:
            status_set_to = MessageStatus.archived

        elif sa.action_type == ActionType.snooze:
            status_set_to = MessageStatus.snoozed

        elif sa.action_type == ActionType.label_remove:
            # If the rule is "remove INBOX", treat as "archive" for DB UX
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
        gmail_attempted=gmail_attempted,
        gmail_threads_targeted=gmail_threads_targeted,
        gmail_threads_changed=gmail_threads_changed,
        gmail_error=gmail_error,
    )
