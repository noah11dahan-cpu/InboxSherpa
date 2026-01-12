from datetime import datetime, timezone
import uuid

import pytest
import httpx
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models import User


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_endpoint_inserts_and_dedupes():
    async with AsyncSessionLocal() as session:
        u = await session.scalar(select(User).where(User.email == "demo@inboxsherpa.local"))
        assert u is not None, "Run python -m app.scripts.seed_dev first"
        user_id = str(u.id)

    run_id = uuid.uuid4().hex[:8]

    msgs = []
    base = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    for i in range(10):
        msgs.append(
            {
                "external_id": f"json-itest-{run_id}-{i}",
                "thread_external_id": f"t-itest-{run_id}",
                "timestamp": base.isoformat(),
                "sender": "tester@example.com",
                "subject": f"Hello {i}",
                "labels": ["WORK"],
            }
        )

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/messages/import", json={"user_id": user_id, "messages": msgs})
        assert r1.status_code == 200, r1.text
        out1 = r1.json()
        assert out1["received"] == 10
        assert out1["inserted"] == 10
        assert out1["deduped"] == 0

        r2 = await client.post("/messages/import", json={"user_id": user_id, "messages": msgs})
        assert r2.status_code == 200, r2.text
        out2 = r2.json()
        assert out2["received"] == 10
        assert out2["inserted"] == 0
        assert out2["deduped"] == 10
