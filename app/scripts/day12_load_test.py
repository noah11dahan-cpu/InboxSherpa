from __future__ import annotations

import argparse
import asyncio
import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models import (
    Channel,
    Message,
    MessageStatus,
    PipelineRun,
)
from app.services.action_rules import propose_actions
from app.services.clustering import cluster_messages_v1
from app.services.suggested_actions import upsert_suggested_action


# -----------------------------
# Helpers (no hardcoding)
# -----------------------------

def _env_int(name: str, default: int | None = None) -> int | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except Exception:
        raise RuntimeError(f"Env var {name} must be an int (got {v!r}).")


def _env_float(name: str, default: float | None = None) -> float | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return float(v)
    except Exception:
        raise RuntimeError(f"Env var {name} must be a float (got {v!r}).")


def _env_str(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def _parse_uuid(s: str) -> uuid.UUID:
    return uuid.UUID(s)


def _local_day_default(tz_name: str) -> date:
    tz = ZoneInfo(tz_name)
    return datetime.now(tz=tz).date()


@dataclass(frozen=True)
class StageTimings:
    insert_ms: int
    clustering_ms: int
    actions_ms: int
    total_ms: int
    clusters_created: int
    actions_created_or_updated: int
    messages_inserted: int


# -----------------------------
# Synthetic data generation
# -----------------------------

_BUCKETS: dict[str, list[str]] = {
    "Promos": ["sale", "deal", "discount", "offer", "promo", "unsubscribe", "newsletter"],
    "School": ["assignment", "quiz", "exam", "deadline", "grades", "course", "canvas"],
    "Bills": ["invoice", "payment", "due", "statement", "receipt", "bank", "credit"],
    "Work": ["meeting", "agenda", "project", "ticket", "review", "standup", "jira"],
    "Social": ["invite", "rsvp", "event", "birthday", "dinner", "party"],
}

_SENDERS = [
    "noreply@amazon.com",
    "billing@bank.com",
    "registrar@university.edu",
    "professor@university.edu",
    "hr@company.com",
    "notifications@github.com",
    "events@social.com",
]

def _rand_subject(rng: random.Random, bucket: str) -> str:
    kw = rng.choice(_BUCKETS.get(bucket, ["update"]))
    templates = [
        f"{kw.title()} update",
        f"Important: {kw}",
        f"{kw.title()} inside",
        f"Re: {kw}",
        f"Your {kw} is ready",
    ]
    return rng.choice(templates)


def _rand_body(rng: random.Random, bucket: str) -> str:
    kws = _BUCKETS.get(bucket, ["update", "info"])
    sample = rng.sample(kws, k=min(3, len(kws)))
    return (
        " ".join([f"This message mentions {w}." for w in sample])
        + " Thanks."
    )


def _timestamp_for_local_day(
    rng: random.Random,
    *,
    digest_date: date,
    tz_name: str,
) -> datetime:
    """
    Create a timestamp that falls on digest_date in tz_name, then convert to UTC.
    This avoids Montreal boundary issues.
    """
    tz = ZoneInfo(tz_name)
    # random time between 08:00 and 22:00 local
    hour = rng.randint(8, 22)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    local_dt = datetime(digest_date.year, digest_date.month, digest_date.day, hour, minute, second, tzinfo=tz)
    return local_dt.astimezone(ZoneInfo("UTC"))


async def _wipe_existing_for_day(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    digest_date: date,
    tz_name: str,
) -> int:
    """
    Deletes JSON-channel messages for that local day (tz_name).
    Returns number deleted.
    """
    local_day_expr = func.date(func.timezone(tz_name, Message.timestamp))
    res = await session.execute(
        delete(Message).where(
            Message.user_id == user_id,
            Message.channel == Channel.json,
            local_day_expr == digest_date,
        )
    )
    return int(res.rowcount or 0)


async def _insert_synthetic_messages(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    digest_date: date,
    tz_name: str,
    count: int,
    seed: int,
    chunk_size: int,
    wipe_existing: bool,
) -> int:
    rng = random.Random(seed)

    if wipe_existing:
        await _wipe_existing_for_day(session, user_id=user_id, digest_date=digest_date, tz_name=tz_name)
        await session.commit()

    buckets = list(_BUCKETS.keys())
    rows_total = 0

    # Insert in chunks for speed
    for start in range(0, count, chunk_size):
        batch_n = min(chunk_size, count - start)
        payload_rows: list[dict] = []
        for i in range(batch_n):
            bucket = rng.choice(buckets)
            sender = rng.choice(_SENDERS)
            subject = _rand_subject(rng, bucket)
            body = _rand_body(rng, bucket)

            external_id = uuid.uuid4().hex
            # group some messages into shared threads
            thread_external_id = f"th_{bucket.lower()}_{rng.randint(1, max(10, count // 50))}"

            ts = _timestamp_for_local_day(rng, digest_date=digest_date, tz_name=tz_name)

            payload_rows.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "thread_id": None,
                    "cluster_id": None,
                    "channel": Channel.json,
                    "external_id": external_id,
                    "thread_external_id": thread_external_id,
                    "timestamp": ts,
                    "sender": sender,
                    "subject": subject,
                    "snippet": subject[:120],
                    "body_text": body,
                    "body_html": None,
                    "labels": ["INBOX"],
                    "history_id": None,
                    "status": MessageStatus.inbox,
                    "raw_payload": {"bucket": bucket},
                    "created_at": _now_utc(),
                }
            )

        await session.execute(insert(Message), payload_rows)
        rows_total += batch_n

    await session.commit()
    return rows_total


# -----------------------------
# Pipeline execution
# -----------------------------

async def _run_pipeline_day12(
    *,
    user_id: uuid.UUID,
    digest_date: date,
    tz_name: str,
    message_count: int,
    seed: int,
    max_seconds: float,
    chunk_size: int,
    wipe_existing: bool,
) -> StageTimings:
    async with AsyncSessionLocal() as session:
        # Stage timing
        t0 = time.perf_counter()

        # PipelineRun row (one row for the whole load test)
        pr = PipelineRun(
            user_id=user_id,
            run_kind="day12_load_test",
            digest_date=digest_date,
            started_at=datetime.utcnow().astimezone(),
            meta=None,
        )
        session.add(pr)
        await session.flush()

        # 1) Insert synthetic messages
        t_insert0 = time.perf_counter()
        inserted = await _insert_synthetic_messages(
            session,
            user_id=user_id,
            digest_date=digest_date,
            tz_name=tz_name,
            count=message_count,
            seed=seed,
            chunk_size=chunk_size,
            wipe_existing=wipe_existing,
        )
        insert_ms = int((time.perf_counter() - t_insert0) * 1000)

        # 2) Cluster
        t_cluster0 = time.perf_counter()
        clusters = await cluster_messages_v1(
            session=session,
            user_id=user_id,
            digest_date=digest_date,
            only_inbox=False,
            limit=message_count,
            rebuild_for_day=True,
            digest_tz=tz_name,
        )
        clustering_ms = int((time.perf_counter() - t_cluster0) * 1000)

        # 3) Propose + upsert actions (same approach as digest endpoint)
        t_actions0 = time.perf_counter()
        actions_written = 0

        for c in clusters:
            msg_rows = await session.execute(
                select(Message.subject, Message.body_text).where(
                    Message.user_id == user_id,
                    Message.cluster_id == c.id,
                )
            )
            msg_pairs = msg_rows.all()
            subjects = [s for (s, _) in msg_pairs if s]
            bodies = [b for (_, b) in msg_pairs if b]

            proposed = propose_actions(
                cluster_title=c.title or "",
                message_subjects=subjects,
                message_bodies=bodies,
            )

            # NOTE: We do not force a default action here. Day12 perf harness should measure rules + upsert only.
            for p in proposed:
                await upsert_suggested_action(
                    session,
                    user_id=user_id,
                    cluster_id=c.id,
                    action_type=p.action_type,
                    payload=p.payload,
                    urgency=p.urgency,
                    confidence=p.confidence,
                )
                actions_written += 1

        await session.commit()
        actions_ms = int((time.perf_counter() - t_actions0) * 1000)

        total_ms = int((time.perf_counter() - t0) * 1000)

        # write PipelineRun meta
        pr.finished_at = datetime.utcnow().astimezone()
        pr.duration_ms = total_ms
        pr.meta = {
            "ok": True,
            "tz_name": tz_name,
            "message_count": message_count,
            "seed": seed,
            "chunk_size": chunk_size,
            "wipe_existing": wipe_existing,
            "insert_ms": insert_ms,
            "clustering_ms": clustering_ms,
            "actions_ms": actions_ms,
            "clusters_created": len(clusters),
            "actions_written": actions_written,
            "max_seconds": max_seconds,
        }
        await session.commit()

        # enforce threshold without hardcoding
        if total_ms > int(max_seconds * 1000):
            raise RuntimeError(f"Day12 load test too slow: {total_ms}ms > {int(max_seconds*1000)}ms")

        return StageTimings(
            insert_ms=insert_ms,
            clustering_ms=clustering_ms,
            actions_ms=actions_ms,
            total_ms=total_ms,
            clusters_created=len(clusters),
            actions_created_or_updated=actions_written,
            messages_inserted=inserted,
        )


# -----------------------------
# CLI
# -----------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Day 12 load test: insert 5k messages -> cluster -> propose actions -> enforce perf budget.")
    p.add_argument("--user-id", type=str, default=_env_str("PIPELINE_USER_ID"), help="UUID of the app user (or env PIPELINE_USER_ID).")
    p.add_argument("--date", type=str, default=_env_str("PIPELINE_DIGEST_DATE"), help="Digest date YYYY-MM-DD (or env PIPELINE_DIGEST_DATE).")
    p.add_argument("--tz", type=str, default=_env_str("PIPELINE_TZ", "America/Montreal"), help="Timezone used for local day bucketing (or env PIPELINE_TZ).")

    p.add_argument("--count", type=int, default=_env_int("PIPELINE_MESSAGE_COUNT", 5000), help="How many messages to insert (or env PIPELINE_MESSAGE_COUNT).")
    p.add_argument("--seed", type=int, default=_env_int("SYNTH_SEED", 42), help="Random seed for deterministic data (or env SYNTH_SEED).")
    p.add_argument("--chunk-size", type=int, default=_env_int("SYNTH_CHUNK_SIZE", 1000), help="Insert chunk size (or env SYNTH_CHUNK_SIZE).")

    p.add_argument("--max-seconds", type=float, default=_env_float("PIPELINE_MAX_SECONDS", 30.0), help="Perf budget in seconds (or env PIPELINE_MAX_SECONDS).")

    p.add_argument("--wipe-existing", action="store_true", default=bool(_env_int("WIPE_EXISTING", 0) == 1), help="Delete existing JSON messages for that day first (or env WIPE_EXISTING=1).")
    return p


async def _amain() -> int:
    args = _build_parser().parse_args()

    if not args.user_id:
        raise RuntimeError("Missing --user-id or env PIPELINE_USER_ID.")
    user_id = _parse_uuid(args.user_id)

    tz_name = args.tz

    if args.date:
        digest_date = _parse_date(args.date)
    else:
        digest_date = _local_day_default(tz_name)

    timings = await _run_pipeline_day12(
        user_id=user_id,
        digest_date=digest_date,
        tz_name=tz_name,
        message_count=int(args.count),
        seed=int(args.seed),
        max_seconds=float(args.max_seconds),
        chunk_size=int(args.chunk_size),
        wipe_existing=bool(args.wipe_existing),
    )

    # stdout summary (useful in CI / recruiter demo)
    print(
        "[day12] OK "
        f"inserted={timings.messages_inserted} "
        f"clusters={timings.clusters_created} "
        f"actions_written={timings.actions_created_or_updated} "
        f"insert_ms={timings.insert_ms} "
        f"clustering_ms={timings.clustering_ms} "
        f"actions_ms={timings.actions_ms} "
        f"total_ms={timings.total_ms}"
    )
    return 0


def main() -> None:
    try:
        asyncio.run(_amain())
    except Exception as e:
        print(f"[day12] FAIL: {e}")
        raise


if __name__ == "__main__":
    main()
