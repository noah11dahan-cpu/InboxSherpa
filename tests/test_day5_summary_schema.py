import pytest
from jsonschema import validate, ValidationError

from app.schemas.summary import ClusterSummaryOut
from app.services.summarizer import summarize_cluster


class Msg:
    def __init__(self, sender: str, subject: str, body_text: str):
        self.sender = sender
        self.subject = subject
        self.snippet = body_text[:120]
        self.body_text = body_text
        self.body_html = None


def test_mock_summary_conforms_to_schema():
    msgs = [
        Msg("Hydro-Québec", "Invoice due tomorrow", "Your payment is due. Final notice."),
        Msg("Hydro-Québec", "Invoice reminder", "Payment due soon."),
        Msg("Bank", "Security alert", "Verify your login activity."),
    ]

    summary = summarize_cluster(msgs, fallback_title="Bills")
    schema = ClusterSummaryOut.model_json_schema()
    validate(instance=summary.model_dump(), schema=schema)


def test_schema_rejects_bad_summary():
    schema = ClusterSummaryOut.model_json_schema()

    bad = {
        "cluster_title": "",
        "summary_bullets": [],
        "urgency": "PANIC",
        "suggested_actions": [{"action_type": "DELETE_ALL", "reason": "lol"}],
        "confidence": 2.0,
    }

    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)
