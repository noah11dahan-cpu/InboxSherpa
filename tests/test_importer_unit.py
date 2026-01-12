import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.importer import NormalizedJsonMessage


def test_normalized_json_message_requires_external_id():
    with pytest.raises(ValidationError):
        NormalizedJsonMessage.model_validate(
            {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "sender": "a@example.com",
                "subject": "hi",
            }
        )


def test_normalized_json_message_parses_ok():
    m = NormalizedJsonMessage.model_validate(
        {
            "external_id": "json-1",
            "thread_external_id": "t-1",
            "timestamp": "2026-01-10T14:30:00Z",
            "sender": "a@example.com",
            "subject": "hello",
            "labels": ["SCHOOL"],
        }
    )
    assert m.external_id == "json-1"
    assert m.thread_external_id == "t-1"
    assert m.labels == ["SCHOOL"]
