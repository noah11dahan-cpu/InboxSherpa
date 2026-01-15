from __future__ import annotations

import json
from pathlib import Path

import pytest
import httpx
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models import User


@pytest.mark.asyncio
async def test_day7_e2e_import_cluster_digest_and_cluster_detail():
    # 1) get demo user without hardcoding
    async with AsyncSessionLocal() as session:
        u = await session.scalar(select(User).where(User.email == "demo@inboxsherpa.local"))
        assert u is not None, "Demo user missing: seed_dev() should create it"
        user_id = str(u.id)

    # 2) load sample inbox dataset from repo (no hardcoding absolute paths)
    p = Path("data/sample_inbox.json")
    assert p.exists(), "Missing data/sample_inbox.json (generate it or commit it)"
    messages = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(messages, list) and len(messages) >= 50

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 3) import messages
        r_import = await client.post("/messages/import", json={"user_id": user_id, "messages": messages})
        assert r_import.status_code == 200, r_import.text
        out = r_import.json()

        assert out["user_id"] == user_id
        assert out["received"] == len(messages)
        # inserted may be < received if test DB already has some messages, but should not error hard
        assert out["errors"] == 0

        # 4) request digest (this triggers clustering if missing)
        digest_date = "2026-01-12"
        r_digest = await client.get(f"/digest/today?user_id={user_id}&digest_date={digest_date}&auto_cluster_if_missing=true")
        assert r_digest.status_code == 200, r_digest.text
        d = r_digest.json()

        assert d["user_id"] == user_id
        assert d["digest_date"] == digest_date
        assert isinstance(d["clusters"], list)
        assert len(d["clusters"]) >= 2

        # 5) validate cluster shape + summary contract
        first = d["clusters"][0]
        assert "cluster_id" in first
        assert "title" in first
        assert "message_count" in first
        assert "summary" in first

        summary = first["summary"]
        assert isinstance(summary["cluster_title"], str) and len(summary["cluster_title"]) >= 2
        assert isinstance(summary["summary_bullets"], list) and len(summary["summary_bullets"]) >= 1
        assert summary["urgency"] in ("low", "medium", "high")
        assert isinstance(summary["suggested_actions"], list)
        assert 0.0 <= float(summary["confidence"]) <= 1.0

        # 6) validate cluster detail endpoint works for UI clicking
        cid = first["cluster_id"]
        r_detail = await client.get(
            f"/clusters/{cid}?user_id={user_id}&digest_date={digest_date}&limit=50"
        )
        assert r_detail.status_code == 200, r_detail.text
        det = r_detail.json()

        assert det["cluster_id"] == cid
        assert det["user_id"] == user_id
        assert det["digest_date"] == digest_date
        assert isinstance(det["messages"], list)
        assert det["message_count"] >= 0
