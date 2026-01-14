from __future__ import annotations
from app.services.summarizer import summarize_cluster
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import sqrt
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cluster, Message, MessageStatus

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# Deterministic label buckets (helps produce human-ish titles like "Promos / School / Bills")
_BUCKETS: dict[str, list[str]] = {
    "Promos": ["unsubscribe", "sale", "deal", "promo", "discount", "offer", "coupon", "newsletter", "marketing"],
    "School": ["assignment", "exam", "quiz", "course", "class", "deadline", "prof", "grades", "moodle", "canvas"],
    "Bills": ["invoice", "bill", "payment", "due", "statement", "receipt", "transaction", "bank", "credit", "rent"],
    "Work": ["meeting", "agenda", "project", "ticket", "jira", "merge", "review", "team", "standup"],
    "Social": ["invite", "rsvp", "event", "birthday", "dinner", "party", "hangout"],
}


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = _HTML_RE.sub(" ", s)  # Gmail HTML bodies later
    s = s.lower()
    s = _WS_RE.sub(" ", s).strip()
    return s


def _guess_bucket(text: str) -> str | None:
    for name, kws in _BUCKETS.items():
        for kw in kws:
            if kw in text:
                return name
    return None


def _choose_k(n: int) -> int:
    """
    Deterministic + conservative:
    - small n => 1–3 clusters
    - larger n => ~sqrt(n), capped
    """
    if n <= 6:
        return 2 if n >= 4 else 1
    k = int(round(sqrt(n)))
    return max(2, min(12, k, n))


def _title_from_terms(terms: list[str]) -> str:
    joined = " ".join(terms)
    b = _guess_bucket(joined)
    if b:
        return b
    # fallback: use the first 1–2 terms
    terms = [t for t in terms if t]
    if not terms:
        return "Other"
    return " / ".join(t.title() for t in terms[:2])


@dataclass(frozen=True)
class ClusterDigestRow:
    cluster_id: str
    title: str
    message_count: int


async def cluster_messages_v1(
    session: AsyncSession,
    *,
    user_id,
    digest_date: date | None = None,
    only_inbox: bool = True,
    limit: int = 5000,
    rebuild_for_day: bool = True,
) -> list[Cluster]:
    """
    Day 4 clustering:
    - Creates Cluster rows for (user_id, digest_date)
    - Assigns Message.cluster_id
    - Deterministic:
        - stable message ordering
        - fixed KMeans random_state
        - fixed vectorizer config
    """
    if digest_date is None:
        digest_date = datetime.now(timezone.utc).date()

    # If rebuilding, delete existing clusters for that day and clear their message assignments
    if rebuild_for_day:
        existing_cluster_ids = await session.scalars(
            select(Cluster.id).where(Cluster.user_id == user_id, Cluster.digest_date == digest_date)
        )
        existing_ids = list(existing_cluster_ids.all())
        if existing_ids:
            await session.execute(
                update(Message)
                .where(Message.user_id == user_id, Message.cluster_id.in_(existing_ids))
                .values(cluster_id=None)
            )
            await session.execute(
                delete(Cluster).where(Cluster.user_id == user_id, Cluster.digest_date == digest_date)
            )
            await session.flush()

    stmt = select(Message).where(Message.user_id == user_id)
    if only_inbox:
        stmt = stmt.where(Message.status == MessageStatus.inbox)
    stmt = stmt.order_by(Message.external_id.asc()).limit(limit)

    res = await session.execute(stmt)
    msgs: list[Message] = list(res.scalars().all())

    if not msgs:
        return []

    docs: list[str] = []
    for m in msgs:
        # Use snippet/body_text as main content; include sender/subject for better topic separation
        doc = " ".join(
            [
                _clean_text(m.subject),
                _clean_text(m.sender),
                _clean_text(m.snippet),
                _clean_text(m.body_text)[:3000],
                _clean_text(m.body_html)[:1000],  # tiny hint even if HTML
            ]
        ).strip()
        docs.append(doc)

    n = len(docs)

    # Very small datasets: deterministic keyword bucketing (no pointless KMeans)
    if n < 8:
        label_map: dict[str, int] = {}
        labels: list[int] = []
        next_id = 0
        for d in docs:
            b = _guess_bucket(d) or "Other"
            if b not in label_map:
                label_map[b] = next_id
                next_id += 1
            labels.append(label_map[b])
        top_terms_by_label: dict[int, list[str]] = {
            lbl: [name.lower()] for name, lbl in label_map.items()
        }
        k = len(label_map)
    else:
        k = _choose_k(n)
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=6000,
            ngram_range=(1, 2),
            min_df=2,
        )
        X = vectorizer.fit_transform(docs)

        km = KMeans(
            n_clusters=k,
            random_state=42,
            n_init=10,
        )
        labels = km.fit_predict(X).tolist()

        feature_names = vectorizer.get_feature_names_out()
        centers = km.cluster_centers_

        top_terms_by_label: dict[int, list[str]] = {}
        for c in range(k):
            # Top centroid features
            top_idx = centers[c].argsort()[::-1][:10]
            terms = [str(feature_names[i]) for i in top_idx if i < len(feature_names)]
            # de-dup but keep order
            seen: set[str] = set()
            uniq: list[str] = []
            for t in terms:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)
            top_terms_by_label[c] = uniq[:8]

    label_to_indices: dict[int, list[int]] = defaultdict(list)
    for i, lbl in enumerate(labels):
        label_to_indices[int(lbl)].append(i)

    created: list[Cluster] = []
    now = datetime.now(timezone.utc)

    # stable cluster order: by size (desc), then label id
    ordered_labels = sorted(
        label_to_indices.keys(),
        key=lambda lbl: (-len(label_to_indices[lbl]), lbl),
    )

    for lbl in ordered_labels:
        idxs = label_to_indices[lbl]
        terms = top_terms_by_label.get(lbl, [])
        if not terms:
            # fallback: most common words across docs in this cluster
            words: list[str] = []
            for i in idxs:
                words.extend([w for w in docs[i].split() if len(w) >= 4])
            terms = [w for w, _ in Counter(words).most_common(8)]

        title = _title_from_terms(terms)
        cluster_msgs = [msgs[i] for i in idxs]
        summary_obj = summarize_cluster(cluster_msgs, fallback_title=title)

        c = Cluster(
            user_id=user_id,
            digest_date=digest_date,
            algo_version="clustering_v1",
            title=summary_obj.cluster_title,
            summary_json=summary_obj.model_dump(),
            created_at=now,
        )
        session.add(c)
        await session.flush()  # get c.id

        # Assign messages to this cluster
        msg_ids = [msgs[i].id for i in idxs]
        await session.execute(
            update(Message).where(Message.id.in_(msg_ids)).values(cluster_id=c.id)
        )

        created.append(c)

    await session.commit()
    return created
