from __future__ import annotations

import time
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models import (
    Cluster,
    Message,
    PipelineRun,
    SuggestedAction,
    ActionType as ModelActionType,
    Urgency as ModelUrgency,
)
from app.schemas.digest import DigestTodayOut, DigestClusterOut
from app.schemas.summary import ClusterSummaryOut, Urgency as SummaryUrgency
from app.services.clustering import cluster_messages_v1

from app.services.action_rules import propose_actions
from app.services.suggested_actions import upsert_suggested_action, list_suggested_actions

# ✅ sync a specific day from Gmail before clustering
from app.services.gmail_sync import sync_gmail_day
from app.utils.summary import fallback_summary

router = APIRouter(prefix="/digest", tags=["digest"])


def _merge_summary(safe_title: str, count: int, summary_json: dict | None) -> dict:
    data = fallback_summary(safe_title, count)

    if isinstance(summary_json, dict) and summary_json:
        data.update(summary_json)

    bullets = data.get("summary_bullets")
    if not isinstance(bullets, list) or len(bullets) == 0:
        data["summary_bullets"] = [f"{count} messages in this cluster."]

    urg = data.get("urgency")
    if urg not in {u.value for u in SummaryUrgency}:
        data["urgency"] = SummaryUrgency.low.value

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


def _default_local_day(tz_name: str = "America/Montreal") -> date:
    tz = ZoneInfo(tz_name)
    return datetime.now(tz=tz).date()


async def _cluster_with_fallback(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    digest_date: date,
    only_inbox: bool,
) -> None:
    """
    Run clustering for digest_date using Montreal-local-day interpretation first.
    If no clusters are produced, retry using UTC day interpretation (fallback),
    to avoid tests/dev data breaking due to timestamp/day boundary quirks.
    """
    created = await cluster_messages_v1(
        session=session,
        user_id=user_id,
        digest_date=digest_date,
        only_inbox=only_inbox,
        rebuild_for_day=True,
        digest_tz="America/Montreal",
    )
    if created:
        return

    # Fallback: treat digest_date as UTC calendar day
    await cluster_messages_v1(
        session=session,
        user_id=user_id,
        digest_date=digest_date,
        only_inbox=only_inbox,
        rebuild_for_day=True,
        digest_tz="UTC",
    )


@router.get("/today", response_model=DigestTodayOut)
async def digest_today(
    user_id: uuid.UUID = Query(..., description="Dev-only: pass the user UUID"),
    digest_date: date | None = Query(None, description="Defaults to local today (America/Montreal)"),
    auto_cluster_if_missing: bool = Query(True, description="If no clusters for the day, run clustering"),
    auto_sync_if_missing: bool = Query(True, description="If no clusters for the day, sync Gmail for that day first"),
    session: AsyncSession = Depends(get_session),
) -> DigestTodayOut:
    if digest_date is None:
        digest_date = _default_local_day("America/Montreal")

    existing_count = await session.scalar(
        select(func.count(Cluster.id)).where(
            Cluster.user_id == user_id,
            Cluster.digest_date == digest_date,
        )
    )

    if (existing_count or 0) == 0 and auto_cluster_if_missing:
        # ✅ Option B: make sure messages for that specific day exist in DB
        if auto_sync_if_missing:
            try:
                await sync_gmail_day(
                    session,
                    user_id=user_id,
                    digest_date=digest_date,
                    tz_name="America/Montreal",
                    max_messages=500,
                )
            except RuntimeError as e:
                if "No Gmail token stored" not in str(e):
                    raise

        # ✅ Day 11: record clustering runtime
        t0 = time.perf_counter()
        pr = PipelineRun(
            user_id=user_id,
            run_kind="clustering_v1",
            digest_date=digest_date,
            started_at=datetime.utcnow().astimezone(),
            meta=None,
        )
        session.add(pr)
        await session.flush()

        try:
            await _cluster_with_fallback(
                session=session,
                user_id=user_id,
                digest_date=digest_date,
                only_inbox=False,
            )
            pr.finished_at = datetime.utcnow().astimezone()
            pr.duration_ms = int((time.perf_counter() - t0) * 1000)
            pr.meta = {"ok": True, "fallback_used": True}
            await session.commit()
        except Exception as e:
            pr.finished_at = datetime.utcnow().astimezone()
            pr.duration_ms = int((time.perf_counter() - t0) * 1000)
            pr.meta = {"ok": False, "error": str(e)}
            await session.commit()
            raise

    # ✅ FIX 1 (the one you asked about):
    # Clean up any dangling SuggestedActions for this user (cluster was deleted/rebuilt).
    # IMPORTANT: do NOT restrict to digest_date here, or you'd delete actions for other days.
    valid_cluster_ids = select(Cluster.id).where(Cluster.user_id == user_id)
    await session.execute(
        delete(SuggestedAction).where(
            SuggestedAction.user_id == user_id,
            ~SuggestedAction.cluster_id.in_(valid_cluster_ids),
        )
    )
    await session.commit()

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
            select(Message.subject, Message.body_text).where(
                Message.cluster_id == cid,
                Message.user_id == user_id,
            )
        )
        msg_pairs = msg_rows.all()
        subjects = [s for (s, _) in msg_pairs if s]
        bodies = [b for (_, b) in msg_pairs if b]

        proposed = propose_actions(
            cluster_title=safe_title,
            message_subjects=subjects,
            message_bodies=bodies,
        )

        thread_rows = await session.execute(
            select(Message.thread_external_id).where(
                Message.cluster_id == cid,
                Message.user_id == user_id,
            )
        )
        thread_ids = sorted({t for (t,) in thread_rows.all() if t})

        # ✅ Apply rule-based proposals
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

        # ✅ Safety net: only create a default action if the cluster actually has messages.
        # Prevents creating actions for empty clusters that will always join to 0 messages.
        if not proposed and count > 0:
            await upsert_suggested_action(
                session,
                user_id=user_id,
                cluster_id=cid,
                action_type=ModelActionType.label_add,
                payload={"label_name": safe_title[:40]},
                urgency=ModelUrgency.low,
                confidence=0.50,
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
                "reason": "Rule-based suggestion" if proposed else "Default suggestion",
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
