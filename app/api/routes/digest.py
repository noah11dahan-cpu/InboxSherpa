from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models import Cluster, Message
from app.schemas.digest import DigestTodayOut, DigestClusterOut
from app.schemas.summary import ClusterSummaryOut, Urgency
from app.services.clustering import cluster_messages_v1

# Day 8
from app.services.action_rules import propose_actions
from app.services.suggested_actions import upsert_suggested_action, list_suggested_actions


router = APIRouter(prefix="/digest", tags=["digest"])


def _fallback_summary(title: str, count: int) -> dict:
    # Ensures schema always present even if old clusters exist without summary_json
    return {
        "cluster_title": title,
        "summary_bullets": [f"{count} messages in this cluster."],
        "urgency": Urgency.low.value,
        "suggested_actions": [],
        "confidence": 0.40,
    }


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
            Cluster.summary_json,
            func.count(Message.id).label("message_count"),
        )
        .join(Message, Message.cluster_id == Cluster.id, isouter=True)
        .where(Cluster.user_id == user_id, Cluster.digest_date == digest_date)
        .group_by(Cluster.id, Cluster.title, Cluster.summary_json)
        .order_by(func.count(Message.id).desc(), Cluster.title.asc())
    )

    clusters: list[DigestClusterOut] = []
    any_db_writes = False

    for (cid, title, summary_json, cnt) in rows.all():
        safe_title = (title or "Other")
        count = int(cnt or 0)

        # base summary (from DB if exists, else fallback)
        data = summary_json or _fallback_summary(safe_title, count)

        # Day 8: propose + persist suggested actions (rule-based)
        msg_rows = await session.execute(
            select(Message.subject, Message.body_text).where(Message.cluster_id == cid, Message.user_id == user_id)
        )
        msg_pairs = msg_rows.all()
        subjects = [s for (s, _) in msg_pairs if s]
        bodies = [b for (_, b) in msg_pairs if b]

        proposed = propose_actions(cluster_title=safe_title, message_subjects=subjects, message_bodies=bodies)

        # For Day 9 Gmail apply: include thread_ids in payload when available
        thread_rows = await session.execute(
            select(Message.thread_external_id).where(Message.cluster_id == cid, Message.user_id == user_id)
        )
        thread_ids = sorted({t for (t,) in thread_rows.all() if t})

        for p in proposed:
            payload = dict(p.payload or {})
            if thread_ids and "thread_ids" not in payload:
                payload["thread_ids"] = thread_ids

            await upsert_suggested_action(
                session,
                user_id=user_id,
                cluster_id=cid,
                action_type=p.action_type,
                payload=payload,
                urgency=p.urgency,
                confidence=p.confidence,
            )
            any_db_writes = True

        actions = await list_suggested_actions(session, user_id=user_id, cluster_id=cid)

        # Inject into the summary returned by API
        # NOTE: ClusterSummaryOut requires suggested_actions[*].reason
        data["suggested_actions"] = [
            {
                "id": str(a.id),
                "action_type": a.action_type.value,
                "payload": a.payload or {},
                "urgency": a.urgency.value,
                "confidence": a.confidence,
                "status": a.status.value,
                "reason": getattr(a, "reason", None) or "Rule-based suggestion",
            }
            for a in actions
        ]

        summary = ClusterSummaryOut.model_validate(data)

        clusters.append(
            DigestClusterOut(
                cluster_id=cid,
                title=safe_title,
                message_count=count,
                summary=summary,
            )
        )

    if any_db_writes:
        await session.commit()

    return DigestTodayOut(user_id=user_id, digest_date=digest_date, clusters=clusters)
