from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cluster, Message, SuggestedAction, PipelineRun, SuggestionStatus


def _env_tz_name(default: str = "America/Montreal") -> str:
    import os
    return (os.getenv("TZ_NAME") or os.getenv("METRICS_TZ_NAME") or default).strip() or default


def _local_today(tz_name: str) -> date:
    tz = ZoneInfo(tz_name)
    return datetime.now(tz=tz).date()


def _day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    local_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


@dataclass(frozen=True)
class MetricsOut:
    user_id: str
    tz_name: str
    day: str  # YYYY-MM-DD

    messages_processed_today: int
    clusters_today: int

    actions_accepted_today: int
    actions_rejected_today: int
    action_acceptance_rate_today: float | None

    avg_clustering_runtime_ms_today: float | None


async def compute_metrics(
    session: AsyncSession,
    *,
    user_id,
    tz_name: str | None = None,
    day: date | None = None,
) -> MetricsOut:
    tz_name = tz_name or _env_tz_name()
    day = day or _local_today(tz_name)

    start_utc, end_utc = _day_bounds_utc(day, tz_name)

    # 1) messages processed today:
    # Use pipeline_runs meta if available (gmail_sync), else fall back to "messages created today".
    pr_q = select(func.coalesce(func.sum((PipelineRun.meta["scanned"].as_integer())), 0)).where(
        PipelineRun.user_id == user_id,
        PipelineRun.run_kind == "gmail_sync",
        PipelineRun.started_at >= start_utc,
        PipelineRun.started_at < end_utc,
    )
    scanned_sum = await session.scalar(pr_q)
    if scanned_sum and int(scanned_sum) > 0:
        messages_processed_today = int(scanned_sum)
    else:
        msg_q = select(func.count()).select_from(Message).where(
            Message.user_id == user_id,
            Message.created_at >= start_utc,
            Message.created_at < end_utc,
        )
        messages_processed_today = int(await session.scalar(msg_q) or 0)

    # 2) cluster count today (clusters keyed by digest_date)
    clusters_q = select(func.count()).select_from(Cluster).where(
        Cluster.user_id == user_id,
        Cluster.digest_date == day,
    )
    clusters_today = int(await session.scalar(clusters_q) or 0)

    # 3) action acceptance rate today (decisions today)
    accepted_q = select(func.count()).select_from(SuggestedAction).where(
        SuggestedAction.user_id == user_id,
        SuggestedAction.status == SuggestionStatus.accepted,
        SuggestedAction.decided_at.is_not(None),
        SuggestedAction.decided_at >= start_utc,
        SuggestedAction.decided_at < end_utc,
    )
    rejected_q = select(func.count()).select_from(SuggestedAction).where(
        SuggestedAction.user_id == user_id,
        SuggestedAction.status == SuggestionStatus.rejected,
        SuggestedAction.decided_at.is_not(None),
        SuggestedAction.decided_at >= start_utc,
        SuggestedAction.decided_at < end_utc,
    )
    actions_accepted_today = int(await session.scalar(accepted_q) or 0)
    actions_rejected_today = int(await session.scalar(rejected_q) or 0)

    denom = actions_accepted_today + actions_rejected_today
    action_acceptance_rate_today = (actions_accepted_today / denom) if denom > 0 else None

    # 4) avg clustering runtime today from pipeline_runs
    avg_cluster_q = select(func.avg(PipelineRun.duration_ms)).where(
        PipelineRun.user_id == user_id,
        PipelineRun.run_kind == "clustering_v1",
        PipelineRun.started_at >= start_utc,
        PipelineRun.started_at < end_utc,
        PipelineRun.duration_ms.is_not(None),
    )
    avg_clustering_runtime_ms_today = await session.scalar(avg_cluster_q)
    if avg_clustering_runtime_ms_today is not None:
        avg_clustering_runtime_ms_today = float(avg_clustering_runtime_ms_today)

    return MetricsOut(
        user_id=str(user_id),
        tz_name=tz_name,
        day=str(day),
        messages_processed_today=messages_processed_today,
        clusters_today=clusters_today,
        actions_accepted_today=actions_accepted_today,
        actions_rejected_today=actions_rejected_today,
        action_acceptance_rate_today=action_acceptance_rate_today,
        avg_clustering_runtime_ms_today=avg_clustering_runtime_ms_today,
    )
