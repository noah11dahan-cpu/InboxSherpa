from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models import Cluster, Message, SuggestedAction
from app.schemas.cluster_detail import ClusterDetailOut, ClusterMessageOut
from app.schemas.summary import ClusterSummaryOut
from app.utils.summary import fallback_summary

router = APIRouter(prefix="/clusters", tags=["clusters"])


def _safe_enum_value(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _pick_reason(sa: SuggestedAction) -> str:
    """
    Your SuggestedAction model does not have .reason (per traceback),
    so we try common alternatives and then fall back.
    """
    for attr in ("reason", "rationale", "description", "explanation"):
        v = getattr(sa, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Rule-based suggestion"


def _serialize_suggested_action(sa: SuggestedAction) -> dict[str, Any] | None:
    """
    Never raise. If a row is missing required fields, skip it (return None).
    """
    try:
        sa_id = getattr(sa, "id", None)
        sa_type = getattr(sa, "action_type", None)
        if sa_id is None or sa_type is None:
            return None

        payload = getattr(sa, "payload", None)
        status = getattr(sa, "status", None)

        # Optional fields (only if your model actually has them)
        urgency = getattr(sa, "urgency", None)
        confidence = getattr(sa, "confidence", None)

        return {
            "id": str(sa_id),
            "action_type": _safe_enum_value(sa_type),
            "reason": _pick_reason(sa),
            "payload": payload,
            "urgency": _safe_enum_value(urgency) if urgency is not None else None,
            "confidence": float(confidence) if confidence is not None else None,
            "status": _safe_enum_value(status) if status is not None else "proposed",
        }
    except Exception:
        return None


@router.get("/{cluster_id}", response_model=ClusterDetailOut)
async def cluster_detail(
    cluster_id: uuid.UUID,
    user_id: uuid.UUID = Query(..., description="Dev-only: pass the user UUID"),
    digest_date: date | None = Query(None, description="Defaults to UTC today"),
    limit: int = Query(200, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
) -> ClusterDetailOut:
    if digest_date is None:
        digest_date = datetime.now(timezone.utc).date()

    cluster = await session.scalar(
        select(Cluster).where(
            Cluster.id == cluster_id,
            Cluster.user_id == user_id,
            Cluster.digest_date == digest_date,
        )
    )
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found for user/date")

    # count messages in cluster
    count = await session.scalar(
        select(func.count(Message.id)).where(
            Message.user_id == user_id,
            Message.cluster_id == cluster_id,
        )
    )
    message_count = int(count or 0)

    # Base summary from Cluster.summary_json, but we will override suggested_actions from DB
    base = cluster.summary_json if isinstance(cluster.summary_json, dict) else {}
    fb = fallback_summary(cluster.title or "Other", message_count)
    summary_data: dict[str, Any] = {**fb, **base}

    # Pull SuggestedAction rows from DB so we have real ids + status
    sa_rows = await session.execute(
        select(SuggestedAction).where(
            SuggestedAction.user_id == user_id,
            SuggestedAction.cluster_id == cluster_id,
        )
    )
    suggested_actions = list(sa_rows.scalars().all())

    serialized = [_serialize_suggested_action(sa) for sa in suggested_actions]
    summary_data["suggested_actions"] = [x for x in serialized if x is not None]

    # Validate into response schema
    summary = ClusterSummaryOut.model_validate(summary_data)

    rows = await session.execute(
        select(Message)
        .where(Message.user_id == user_id, Message.cluster_id == cluster_id)
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    msgs = list(rows.scalars().all())

    return ClusterDetailOut(
        user_id=user_id,
        digest_date=digest_date,
        cluster_id=cluster.id,
        title=cluster.title or "Other",
        message_count=message_count,
        summary=summary,
        messages=[
            ClusterMessageOut(
                id=str(m.id),
                external_id=str(m.external_id),
                sender=m.sender,
                subject=m.subject,
                snippet=m.snippet,
                timestamp=m.timestamp,
                status=m.status.value if hasattr(m.status, "value") else str(m.status),
                channel=m.channel.value if hasattr(m.channel, "value") else str(m.channel),
            )
            for m in msgs
        ],
    )
