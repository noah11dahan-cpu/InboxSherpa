from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.services.metrics import compute_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def get_metrics(
    user_id: uuid.UUID = Query(...),
    tz_name: str | None = Query(None),
    day: date | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    out = await compute_metrics(session, user_id=user_id, tz_name=tz_name, day=day)
    return {
        "user_id": out.user_id,
        "tz_name": out.tz_name,
        "day": out.day,
        "messages_processed_today": out.messages_processed_today,
        "clusters_today": out.clusters_today,
        "actions_accepted_today": out.actions_accepted_today,
        "actions_rejected_today": out.actions_rejected_today,
        "action_acceptance_rate_today": out.action_acceptance_rate_today,
        "avg_clustering_runtime_ms_today": out.avg_clustering_runtime_ms_today,
    }
