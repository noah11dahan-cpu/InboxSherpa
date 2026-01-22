from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SuggestedAction, ActionType, Urgency, SuggestionStatus


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_suggested_action(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    cluster_id: uuid.UUID,
    action_type: ActionType,
    payload: dict | None,
    urgency: Urgency,
    confidence: float | None,
) -> SuggestedAction:
    """
    Upsert rule-proposed suggestions.
    - Dedupe key (v1): (user_id, cluster_id, action_type)
    - Never overwrite accepted/rejected
    - Update payload/urgency/confidence if still proposed
    - IMPORTANT: If we update an existing proposed suggestion, bump created_at so "latest proposed"
      corresponds to the most recently generated suggestion for test determinism.
    """
    existing = await session.scalar(
        select(SuggestedAction).where(
            SuggestedAction.user_id == user_id,
            SuggestedAction.cluster_id == cluster_id,
            SuggestedAction.action_type == action_type,
        )
    )

    if existing is not None:
        if existing.status != SuggestionStatus.proposed:
            return existing

        existing.payload = payload
        existing.urgency = urgency
        existing.confidence = confidence

        # ✅ Make it "latest" for tests / UI freshness
        existing.created_at = _now_utc()
        return existing

    sa = SuggestedAction(
        user_id=user_id,
        cluster_id=cluster_id,
        action_type=action_type,
        payload=payload,
        urgency=urgency,
        confidence=confidence,
        status=SuggestionStatus.proposed,
        created_at=_now_utc(),  # optional but keeps it consistent
    )
    session.add(sa)
    return sa


async def list_suggested_actions(
    session: AsyncSession, *, user_id: uuid.UUID, cluster_id: uuid.UUID
) -> list[SuggestedAction]:
    res = await session.execute(
        select(SuggestedAction)
        .where(SuggestedAction.user_id == user_id, SuggestedAction.cluster_id == cluster_id)
        .order_by(SuggestedAction.created_at.desc())
    )
    return list(res.scalars().all())
