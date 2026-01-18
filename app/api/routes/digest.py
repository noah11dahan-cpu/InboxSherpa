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

from app.services.action_rules import propose_actions
from app.services.suggested_actions import upsert_suggested_action, list_suggested_actions

# ✅ NEW: sync a specific day from Gmail before clustering
from app.services.gmail_sync import sync_gmail_day

router = APIRouter(prefix="/digest", tags=["digest"])


def _fallback_summary(title: str, count: int) -> dict:
    return {
        "cluster_title": title,
        "summary_bullets": [f"{count} messages in this cluster."],
        "urgency": Urgency.low.value,
        "suggested_actions": [],
        "confidence": 0.40,
    }


def _merge_summary(safe_title: str, count: int, summary_json: dict | None) -> dict:
    data = _fallback_summary(safe_title, count)

    if isinstance(summary_json, dict) and summary_json:
        data.update(summary_json)

    bullets = data.get("summary_bullets")
    if not isinstance(bullets, list) or len(bullets) == 0:
        data["summary_bullets"] = [f"{count} messages in this cluster."]

    urg = data.get("urgency")
    if urg not in {u.value for u in Urgency}:
        data["urgency"] = Urgency.low.value

    conf = data.get("confidence")
    try:
        conf_f = float(conf)
    except Exception:
        conf_f = 0.40
    if conf_f < 0.0:
        conf_f = 0.0
    if conf_f > 1.0:
        conf_f = 1.0
    data["confidence"] = conf_f

    ct = data.get("cluster_title")
    if not isinstance(ct, str) or not ct.strip():
        data["cluster_title"] = safe_title

    return data


@router.get("/today", response_model=DigestTodayOut)
async def digest_today(
    user_id: uuid.UUID = Query(..., description="Dev-only: pass the user UUID"),
    digest_date: date | None = Query(None, description="Defaults to UTC today"),
    auto_cluster_if_missing: bool = Query(True, description="If no clusters for the day, run clustering"),
    # ✅ NEW: if missing, sync that day from Gmail first
    auto_sync_if_missing: bool = Query(True, description="If no clusters for the day, sync Gmail for that day first"),
    session: AsyncSession = Depends(get_session),
) -> DigestTodayOut:
    if digest_date is None:
        digest_date = datetime.now(timezone.utc).date()

    existing_count = await session.scalar(
        select(func.count(Cluster.id)).where(Cluster.user_id == user_id, Cluster.digest_date == digest_date)
    )

    if (existing_count or 0) == 0 and auto_cluster_if_missing:
        # ✅ Option B: make sure messages for that specific day exist in DB
        if auto_sync_if_missing:
            # This is safe: it dedupes on insert by unique constraint.
            await sync_gmail_day(session, user_id=user_id, digest_date=digest_date, tz_name="America/Montreal", max_messages=500)

        await cluster_messages_v1(
            session=session,
            user_id=user_id,
            digest_date=digest_date,
            only_inbox=False,
            rebuild_for_day=True,
        )

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

        data = _merge_summary(safe_title, count, summary_json)

        msg_rows = await session.execute(
            select(Message.subject, Message.body_text).where(Message.cluster_id == cid, Message.user_id == user_id)
        )
        msg_pairs = msg_rows.all()
        subjects = [s for (s, _) in msg_pairs if s]
        bodies = [b for (_, b) in msg_pairs if b]

        proposed = propose_actions(cluster_title=safe_title, message_subjects=subjects, message_bodies=bodies)

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

        data["suggested_actions"] = [
            {
                "id": str(a.id),
                "action_type": a.action_type.value,
                "payload": a.payload or {},
                "urgency": a.urgency.value,
                "confidence": a.confidence,
                "status": a.status.value,
                "reason": "Rule-based suggestion",
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
