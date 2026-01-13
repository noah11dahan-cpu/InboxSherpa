from __future__ import annotations

import uuid
from datetime import date
from pydantic import BaseModel


class DigestClusterOut(BaseModel):
    cluster_id: uuid.UUID
    title: str
    message_count: int


class DigestTodayOut(BaseModel):
    user_id: uuid.UUID
    digest_date: date
    clusters: list[DigestClusterOut]
