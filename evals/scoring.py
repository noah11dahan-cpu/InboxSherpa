"""
Scoring harness for evaluating cluster summaries.

Checks:
- Relevance: keyword overlap between messages and summary
- Brevity: summary bullets within length constraints
- Urgency sanity: urgency level matches message content
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

# Stop words to ignore in keyword extraction
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "with",
    "re", "fw", "fwd", "your", "you", "from", "at", "is", "are", "this",
    "that", "it", "be", "has", "have", "had", "was", "were", "been", "will",
    "would", "could", "should", "can", "may", "might", "must", "do", "does",
    "did", "no", "not", "but", "if", "so", "as", "by", "up", "out", "about",
    "into", "over", "after", "before", "between", "under", "again", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "few", "more", "most", "other", "some", "such", "only", "own", "same",
    "than", "too", "very", "just", "also", "now", "new", "one", "two",
}

# Patterns indicating urgency
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
    r"\bexpir",
    r"\bimmediate\b",
    r"\basap\b",
    r"\btime.?sensitive\b",
]


@dataclass
class ScoreResult:
    """Result of scoring a single summary."""
    test_id: str
    relevance_score: float  # 0.0 - 1.0
    brevity_score: float    # 0.0 - 1.0
    urgency_score: float    # 0.0 - 1.0
    overall_score: float    # weighted average
    passed: bool
    details: dict = field(default_factory=dict)


@dataclass
class EvalReport:
    """Aggregated evaluation report."""
    total_tests: int
    passed_tests: int
    failed_tests: int
    avg_relevance: float
    avg_brevity: float
    avg_urgency: float
    avg_overall: float
    pass_rate: float
    individual_results: List[ScoreResult] = field(default_factory=list)


def _extract_keywords(text: str) -> Set[str]:
    """Extract meaningful keywords from text."""
    if not text:
        return set()
    # Normalize and tokenize
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    tokens = text.split()
    # Filter short words and stop words
    return {t for t in tokens if len(t) >= 3 and t not in _STOP_WORDS}


def _count_urgent_matches(text: str) -> int:
    """Count how many urgency patterns match in text."""
    text_lower = text.lower()
    return sum(1 for pat in _URGENT_PATTERNS if re.search(pat, text_lower))


def score_relevance(
    message_subjects: List[str],
    message_bodies: List[str],
    summary_title: str,
    summary_bullets: List[str],
) -> tuple[float, dict]:
    """
    Score relevance via keyword overlap.

    Returns (score, details) where score is 0.0-1.0.
    """
    # Extract keywords from messages
    msg_text = " ".join(message_subjects + message_bodies)
    msg_keywords = _extract_keywords(msg_text)

    # Extract keywords from summary
    summary_text = summary_title + " " + " ".join(summary_bullets)
    summary_keywords = _extract_keywords(summary_text)

    if not msg_keywords:
        # No keywords in messages = can't evaluate relevance meaningfully
        return 0.5, {"reason": "no_message_keywords", "overlap": 0}

    if not summary_keywords:
        return 0.0, {"reason": "no_summary_keywords", "overlap": 0}

    # Calculate Jaccard-like overlap
    overlap = msg_keywords & summary_keywords

    # Weight by how much of the summary keywords come from messages
    # (summary should use message vocabulary)
    precision = len(overlap) / len(summary_keywords) if summary_keywords else 0
    recall = len(overlap) / len(msg_keywords) if msg_keywords else 0

    # F1-like score
    if precision + recall == 0:
        score = 0.0
    else:
        score = 2 * (precision * recall) / (precision + recall)

    return score, {
        "msg_keyword_count": len(msg_keywords),
        "summary_keyword_count": len(summary_keywords),
        "overlap_count": len(overlap),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
    }


def score_brevity(
    summary_title: str,
    summary_bullets: List[str],
    max_title_len: int = 80,
    max_bullets: int = 6,
    max_bullet_len: int = 200,
) -> tuple[float, dict]:
    """
    Score brevity constraints.

    Checks:
    - Title length <= max_title_len
    - Number of bullets <= max_bullets
    - Each bullet length <= max_bullet_len
    """
    penalties = []

    # Title length check
    title_len = len(summary_title)
    if title_len > max_title_len:
        penalties.append(("title_too_long", 0.3))
    elif title_len < 2:
        penalties.append(("title_too_short", 0.2))

    # Bullet count check
    bullet_count = len(summary_bullets)
    if bullet_count > max_bullets:
        penalties.append(("too_many_bullets", 0.3))
    elif bullet_count < 1:
        penalties.append(("no_bullets", 0.4))

    # Individual bullet length check
    long_bullets = sum(1 for b in summary_bullets if len(b) > max_bullet_len)
    if long_bullets > 0:
        penalties.append(("bullets_too_long", 0.1 * long_bullets))

    # Empty bullets check
    empty_bullets = sum(1 for b in summary_bullets if not b.strip())
    if empty_bullets > 0:
        penalties.append(("empty_bullets", 0.2 * empty_bullets))

    total_penalty = sum(p[1] for p in penalties)
    score = max(0.0, 1.0 - total_penalty)

    return score, {
        "title_len": title_len,
        "bullet_count": bullet_count,
        "long_bullets": long_bullets,
        "empty_bullets": empty_bullets,
        "penalties": [p[0] for p in penalties],
    }


def score_urgency(
    message_subjects: List[str],
    message_bodies: List[str],
    declared_urgency: str,
) -> tuple[float, dict]:
    """
    Score urgency sanity - does declared urgency match message content?

    urgency should be "low", "medium", or "high"
    """
    # Count urgent patterns in messages
    msg_text = " ".join(message_subjects + message_bodies)
    urgent_matches = _count_urgent_matches(msg_text)

    # Determine expected urgency based on matches
    if urgent_matches >= 3:
        expected = "high"
    elif urgent_matches >= 1:
        expected = "medium"
    else:
        expected = "low"

    # Score based on match
    declared = declared_urgency.lower()

    if declared == expected:
        score = 1.0
    elif abs(_urgency_to_int(declared) - _urgency_to_int(expected)) == 1:
        # Off by one level is acceptable
        score = 0.7
    else:
        # Off by two levels
        score = 0.3

    return score, {
        "urgent_pattern_matches": urgent_matches,
        "expected_urgency": expected,
        "declared_urgency": declared,
        "match": declared == expected,
    }


def _urgency_to_int(urgency: str) -> int:
    """Convert urgency string to int for comparison."""
    return {"low": 0, "medium": 1, "high": 2}.get(urgency.lower(), 0)


def score_summary(
    test_id: str,
    message_subjects: List[str],
    message_bodies: List[str],
    summary_title: str,
    summary_bullets: List[str],
    declared_urgency: str,
    pass_threshold: float = 0.6,
    weights: tuple[float, float, float] = (0.5, 0.25, 0.25),
) -> ScoreResult:
    """
    Score a single summary against messages.

    Args:
        test_id: Identifier for this test case
        message_subjects: List of message subjects
        message_bodies: List of message body texts
        summary_title: Generated summary title
        summary_bullets: Generated summary bullets
        declared_urgency: Declared urgency level
        pass_threshold: Minimum overall score to pass
        weights: (relevance_weight, brevity_weight, urgency_weight)

    Returns:
        ScoreResult with all scores and pass/fail status
    """
    rel_score, rel_details = score_relevance(
        message_subjects, message_bodies, summary_title, summary_bullets
    )

    brev_score, brev_details = score_brevity(summary_title, summary_bullets)

    urg_score, urg_details = score_urgency(
        message_subjects, message_bodies, declared_urgency
    )

    # Weighted average
    w_rel, w_brev, w_urg = weights
    overall = (rel_score * w_rel + brev_score * w_brev + urg_score * w_urg)

    return ScoreResult(
        test_id=test_id,
        relevance_score=round(rel_score, 3),
        brevity_score=round(brev_score, 3),
        urgency_score=round(urg_score, 3),
        overall_score=round(overall, 3),
        passed=overall >= pass_threshold,
        details={
            "relevance": rel_details,
            "brevity": brev_details,
            "urgency": urg_details,
        },
    )


def aggregate_results(results: List[ScoreResult]) -> EvalReport:
    """Aggregate individual results into a report."""
    if not results:
        return EvalReport(
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            avg_relevance=0.0,
            avg_brevity=0.0,
            avg_urgency=0.0,
            avg_overall=0.0,
            pass_rate=0.0,
            individual_results=[],
        )

    n = len(results)
    passed = sum(1 for r in results if r.passed)

    return EvalReport(
        total_tests=n,
        passed_tests=passed,
        failed_tests=n - passed,
        avg_relevance=round(sum(r.relevance_score for r in results) / n, 3),
        avg_brevity=round(sum(r.brevity_score for r in results) / n, 3),
        avg_urgency=round(sum(r.urgency_score for r in results) / n, 3),
        avg_overall=round(sum(r.overall_score for r in results) / n, 3),
        pass_rate=round(passed / n, 3),
        individual_results=results,
    )
