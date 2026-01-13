import uuid
import pytest
import httpx

from app.main import app

USER_ID = uuid.UUID("96cd6791-db08-4723-9b61-36377b9f6c9a")


@pytest.mark.asyncio
async def test_day4_digest_returns_clusters_for_user():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/digest/today?user_id={USER_ID}&digest_date=2026-01-12")
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["user_id"] == str(USER_ID)
        assert data["digest_date"] == "2026-01-12"
        assert isinstance(data["clusters"], list)
        assert len(data["clusters"]) >= 1
