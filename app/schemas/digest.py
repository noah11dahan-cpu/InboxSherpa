from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.summary import ClusterSummaryOut


class DigestClusterOut(BaseModel):
    cluster_id: uuid.UUID
    title: str
    message_count: int
    summary: ClusterSummaryOut


class DigestTodayOut(BaseModel):
    user_id: uuid.UUID
    digest_date: date
    clusters: list[DigestClusterOut]
