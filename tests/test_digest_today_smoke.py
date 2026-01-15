import pytest
import httpx
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models import User


@pytest.mark.asyncio
async def test_digest_today_smoke():
    async with AsyncSessionLocal() as session:
        u = await session.scalar(select(User).where(User.email == "demo@inboxsherpa.local"))
        assert u is not None
        user_id = str(u.id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/digest/today?user_id={user_id}&digest_date=2026-01-12")
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["user_id"] == user_id
        assert data["digest_date"] == "2026-01-12"
        assert isinstance(data["clusters"], list)
