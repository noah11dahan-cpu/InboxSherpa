from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models import Cluster, Message
from app.schemas.cluster_detail import ClusterDetailOut, ClusterMessageOut
from app.schemas.summary import ClusterSummaryOut, Urgency

router = APIRouter(prefix="/clusters", tags=["clusters"])


def _fallback_summary(title: str, count: int) -> dict:
    return {
        "cluster_title": title,
        "summary_bullets": [f"{count} messages in this cluster."],
        "urgency": Urgency.low.value,
        "suggested_actions": [],
        "confidence": 0.40,
    }


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
        select(func.count(Message.id)).where(Message.user_id == user_id, Message.cluster_id == cluster_id)
    )
    message_count = int(count or 0)

    summary_data = cluster.summary_json or _fallback_summary(cluster.title or "Other", message_count)
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
                id=m.id,
                external_id=m.external_id,
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
