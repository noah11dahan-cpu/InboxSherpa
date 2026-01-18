from __future__ import annotations

import json
from pathlib import Path

import pytest
import httpx
from sqlalchemy import select, func

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models import User, SuggestedAction


@pytest.mark.asyncio
async def test_day8_suggested_actions_created_after_digest():
    # 1) get demo user without hardcoding
    async with AsyncSessionLocal() as session:
        u = await session.scalar(select(User).where(User.email == "demo@inboxsherpa.local"))
        assert u is not None, "Demo user missing: seed_dev() should create it"
        user_id = str(u.id)

    # 2) load sample inbox dataset from repo
    p = Path("data/sample_inbox.json")
    assert p.exists(), "Missing data/sample_inbox.json (generate it or commit it)"
    messages = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(messages, list) and len(messages) >= 1

    # 3) append a guaranteed-promos message (clone shape from an existing message)
    m0 = dict(messages[0])
    m0["external_id"] = str(m0.get("external_id", "x")) + "-day8-promos"
    m0["subject"] = "Big Sale - 70% Discount"
    if "body_text" in m0:
        m0["body_text"] = "Limited time promotion. Use coupon code."
    messages.append(m0)

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 4) import messages
        r_import = await client.post("/messages/import", json={"user_id": user_id, "messages": messages})
        assert r_import.status_code == 200, r_import.text

        # 5) request digest (triggers clustering + Day 8 actions)
        digest_date = "2026-01-12"
        r_digest = await client.get(
            f"/digest/today?user_id={user_id}&digest_date={digest_date}&auto_cluster_if_missing=true"
        )
        assert r_digest.status_code == 200, r_digest.text

    # 6) verify SuggestedAction rows exist for that user
    async with AsyncSessionLocal() as session:
        n = await session.scalar(select(func.count(SuggestedAction.id)).where(SuggestedAction.user_id == u.id))
        assert (n or 0) >= 1, "Expected at least 1 suggested action after digest generation"
