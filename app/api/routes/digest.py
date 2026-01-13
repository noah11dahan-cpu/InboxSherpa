from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models import Cluster, Message
from app.schemas.digest import DigestTodayOut, DigestClusterOut
from app.services.clustering import cluster_messages_v1

router = APIRouter(prefix="/digest", tags=["digest"])


@router.get("/today", response_model=DigestTodayOut)
async def digest_today(
    user_id: uuid.UUID = Query(..., description="Dev-only: pass the user UUID"),
    digest_date: date | None = Query(None, description="Defaults to UTC today"),
    auto_cluster_if_missing: bool = Query(True, description="If no clusters for the day, run clustering"),
    session: AsyncSession = Depends(get_session),
) -> DigestTodayOut:
    if digest_date is None:
        digest_date = datetime.now(timezone.utc).date()

    # If nothing exists for that day, optionally run clustering
    existing_count = await session.scalar(
        select(func.count(Cluster.id)).where(Cluster.user_id == user_id, Cluster.digest_date == digest_date)
    )
    if (existing_count or 0) == 0 and auto_cluster_if_missing:
        await cluster_messages_v1(session=session, user_id=user_id, digest_date=digest_date)

    rows = await session.execute(
        select(
            Cluster.id,
            Cluster.title,
            func.count(Message.id).label("message_count"),
        )
        .join(Message, Message.cluster_id == Cluster.id, isouter=True)
        .where(Cluster.user_id == user_id, Cluster.digest_date == digest_date)
        .group_by(Cluster.id, Cluster.title)
        .order_by(func.count(Message.id).desc(), Cluster.title.asc())
    )

    clusters = [
        DigestClusterOut(
            cluster_id=cid,
            title=(title or "Other"),
            message_count=int(cnt or 0),
        )
        for (cid, title, cnt) in rows.all()
    ]

    return DigestTodayOut(user_id=user_id, digest_date=digest_date, clusters=clusters)
