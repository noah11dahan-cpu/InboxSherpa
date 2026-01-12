from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


SourceType = Literal["json"]


class ImportRequest(BaseModel):
    # Mode B: user_id provided directly
    user_id: uuid.UUID

    # Provide either inline messages or a server-side file path
    messages: Optional[list[dict[str, Any]]] = None
    file_path: Optional[str] = None

    source: SourceType = "json"
    allow_file_path: bool = True


class ImportResult(BaseModel):
    user_id: uuid.UUID
    received: int
    inserted: int
    deduped: int
    errors: int


class NormalizedJsonMessage(BaseModel):
    """
    Day 3 normalized JSON message schema.

    external_id is REQUIRED because:
    - Message.external_id is NOT NULL
    - UniqueConstraint(user_id, channel, external_id) is your dedupe key
    """
    external_id: str
    thread_external_id: Optional[str] = None

    timestamp: datetime

    sender: str
    subject: str
    snippet: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None

    labels: list[str] = Field(default_factory=list)
    raw_payload: Optional[dict[str, Any]] = None
