from __future__ import annotations

import uuid
from datetime import date, datetime
from pydantic import BaseModel

from app.schemas.summary import ClusterSummaryOut


class ClusterMessageOut(BaseModel):
    id: uuid.UUID
    external_id: str
    channel: str
    timestamp: datetime
    sender: str
    subject: str
    snippet: str | None
    status: str


class ClusterDetailOut(BaseModel):
    user_id: uuid.UUID
    digest_date: date
    cluster_id: uuid.UUID
    title: str
    message_count: int
    summary: ClusterSummaryOut
    messages: list[ClusterMessageOut]
