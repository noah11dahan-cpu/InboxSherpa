from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, conlist, confloat


class Urgency(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ActionType(str, Enum):
    # Match your DB enum values in app/models.py exactly
    archive_all = "archive_all"
    snooze = "snooze"
    reply_with_template = "reply_with_template"
    label_add = "label_add"
    label_remove = "label_remove"

class SuggestionStatus(str, Enum):
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"

class SuggestedActionOut(BaseModel):
    id: str
    action_type: ActionType
    reason: str = Field(..., min_length=3, max_length=240)
    payload: dict | None = None
    urgency: Urgency | None = None
    confidence: float | None = None
    status: SuggestionStatus = SuggestionStatus.proposed




class ClusterSummaryOut(BaseModel):
    cluster_title: str = Field(..., min_length=2, max_length=80)
    summary_bullets: conlist(str, min_length=1, max_length=6)  # type: ignore[valid-type]
    urgency: Urgency
    suggested_actions: List[SuggestedActionOut] = Field(default_factory=list)
    confidence: confloat(ge=0.0, le=1.0)  # type: ignore[valid-type]
