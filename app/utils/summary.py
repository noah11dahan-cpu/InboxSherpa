"""Shared summary utilities for digest and cluster routes."""
from __future__ import annotations

from typing import Any

from app.schemas.summary import Urgency


def fallback_summary(title: str, count: int) -> dict[str, Any]:
    """Return a minimal cluster summary when no ML-generated summary is available."""
    return {
        "cluster_title": title,
        "summary_bullets": [f"{count} messages in this cluster."],
        "urgency": Urgency.low.value,
        "suggested_actions": [],
        "confidence": 0.40,
    }
