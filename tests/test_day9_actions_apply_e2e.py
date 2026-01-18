from __future__ import annotations

import json
from pathlib import Path

import pytest
import httpx
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models import User, SuggestedAction, SuggestionStatus, ActionType, Message, MessageStatus


@pytest.mark.asyncio
async def test_day9_apply_accept_updates_db_statuses():
    # 1) get demo user
    async with AsyncSessionLocal() as session:
        u = await session.scalar(select(User).where(User.email == "demo@inboxsherpa.local"))
        assert u is not None, "Demo user missing: seed_dev() should create it"
        user_id = str(u.id)

    # 2) load sample inbox dataset
    p = Path("data/sample_inbox.json")
    assert p.exists(), "Missing data/sample_inbox.json"
    messages = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(messages, list) and len(messages) >= 1

    # 3) Add a guaranteed promos message to trigger archive_all (per your rules)
    m0 = dict(messages[0])
    m0["external_id"] = str(m0.get("external_id", "x")) + "-day9-promos"
    m0["subject"] = "Big Sale - 90% Discount"
    if "body_text" in m0:
        m0["body_text"] = "Limited time promotion. Use coupon code."
    messages.append(m0)

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 4) import
        r_import = await client.post("/messages/import", json={"user_id": user_id, "messages": messages})
        assert r_import.status_code == 200, r_import.text

        # 5) request digest (creates suggested actions)
        digest_date = "2026-01-12"
        r_digest = await client.get(f"/digest/today?user_id={user_id}&digest_date={digest_date}&auto_cluster_if_missing=true")
        assert r_digest.status_code == 200, r_digest.text

    # 6) find a proposed archive_all action
    async with AsyncSessionLocal() as session:
        sa = await session.scalar(
            select(SuggestedAction)
            .where(SuggestedAction.user_id == u.id, SuggestedAction.status == SuggestionStatus.proposed)
            .order_by(SuggestedAction.created_at.desc())
        )
        assert sa is not None, "Expected at least one proposed SuggestedAction"
        sa_id = str(sa.id)

    # 7) apply accept
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r_apply = await client.post(
            "/actions/apply",
            json={"user_id": user_id, "suggested_action_id": sa_id, "decision": "accept"},
        )
        assert r_apply.status_code == 200, r_apply.text

    # 8) verify DB changed
    async with AsyncSessionLocal() as session:
        sa2 = await session.scalar(select(SuggestedAction).where(SuggestedAction.id == sa.id))
        assert sa2 is not None
        assert sa2.status == SuggestionStatus.accepted
        assert sa2.decided_at is not None

        # If this was archive_all or snooze, messages in that cluster should no longer be inbox
        if sa2.action_type in (ActionType.archive_all, ActionType.snooze):
            msgs = (await session.execute(
                select(Message).where(
                    Message.user_id == u.id,
                    Message.cluster_id == sa2.cluster_id,
                )
            )).scalars().all()
            assert len(msgs) >= 1
            assert all(m.status != MessageStatus.inbox for m in msgs), "Expected cluster messages to move out of inbox"
