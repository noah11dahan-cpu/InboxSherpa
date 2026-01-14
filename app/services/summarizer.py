from __future__ import annotations

import re
from collections import Counter
from typing import List

from app.models import Message
from app.schemas.summary import ActionType, ClusterSummaryOut, SuggestedActionOut, Urgency

_STOP = {
    "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "with", "re", "fw",
    "your", "you", "from", "at", "is", "are", "this", "that", "it",
}

_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^a-zA-Z0-9\s]")

_URGENT_PATTERNS = [
    r"\baction required\b",
    r"\burgent\b",
    r"\bdeadline\b",
    r"\bdue\b",
    r"\boverdue\b",
    r"\bpayment\b",
    r"\binvoice\b",
    r"\bsecurity\b",
    r"\bverify\b",
    r"\bfinal notice\b",
]


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return _WS.sub(" ", s.strip().lower())


def _tokens(s: str) -> List[str]:
    s = _NONWORD.sub(" ", s)
    out: List[str] = []
    for t in s.lower().split():
        if len(t) >= 3 and t not in _STOP:
            out.append(t)
    return out


def _top_keywords(subjects: List[str], k: int = 3) -> List[str]:
    c = Counter()
    for subj in subjects:
        for t in _tokens(subj):
            c[t] += 1
    return [w for w, _ in c.most_common(k)]


def _compute_urgency(msgs: List[Message]) -> Urgency:
    blob = " ".join(
        _norm(m.subject) + " " + _norm(m.snippet) + " " + _norm(m.body_text) + " " + _norm(m.body_html)
        for m in msgs
    )
    hits = sum(1 for pat in _URGENT_PATTERNS if re.search(pat, blob))
    if hits >= 2:
        return Urgency.high
    if hits == 1:
        return Urgency.medium
    return Urgency.low


def _suggest_actions(title: str, urgency: Urgency) -> List[SuggestedActionOut]:
    t = title.lower()
    actions: List[SuggestedActionOut] = []

    if any(w in t for w in ["promo", "sale", "deal", "newsletter", "marketing", "unsubscribe"]):
        actions.append(
            SuggestedActionOut(
                action_type=ActionType.archive_all,
                reason="Looks like promotional content; archive after a quick scan.",
            )
        )

    if urgency in (Urgency.medium, Urgency.high):
        actions.append(
            SuggestedActionOut(
                action_type=ActionType.snooze,
                reason="Contains deadline/payment/security language; snooze if you can’t act now.",
                payload={"snooze_for_hours": 24},
            )
        )

    # Gmail-ready labeling primitive
    actions.append(
        SuggestedActionOut(
            action_type=ActionType.label_add,
            reason="Apply a topic label to keep this cluster organized.",
            payload={"label_name": title[:40]},
        )
    )

    return actions


def summarize_cluster(msgs: List[Message], *, fallback_title: str) -> ClusterSummaryOut:
    if not msgs:
        return ClusterSummaryOut(
            cluster_title=fallback_title,
            summary_bullets=["No messages found in this cluster."],
            urgency=Urgency.low,
            suggested_actions=[],
            confidence=0.30,
        )

    subjects = [_norm(m.subject) for m in msgs if m.subject]
    senders = [_norm(m.sender) for m in msgs if m.sender]

    top_sender = None
    top_sender_n = 0
    if senders:
        top_sender, top_sender_n = Counter(senders).most_common(1)[0]

    keywords = _top_keywords(subjects, k=3)
    title = " / ".join([kw.capitalize() for kw in keywords]) if keywords else fallback_title

    urgency = _compute_urgency(msgs)

    bullets: List[str] = [f"{len(msgs)} messages in this cluster."]
    if top_sender and top_sender_n >= 2:
        bullets.append(f"Most frequent sender: {top_sender} ({top_sender_n}).")
    if keywords:
        bullets.append(f"Common topics: {', '.join(keywords[:3])}.")
    if urgency == Urgency.high:
        bullets.append("Contains urgent language (deadline/payment/security).")

    confidence = 0.55
    if len(msgs) >= 5:
        confidence += 0.10
    if keywords:
        confidence += 0.10
    if urgency != Urgency.low:
        confidence += 0.05
    confidence = min(confidence, 0.95)

    return ClusterSummaryOut(
        cluster_title=title,
        summary_bullets=bullets[:6],
        urgency=urgency,
        suggested_actions=_suggest_actions(title, urgency),
        confidence=confidence,
    )
