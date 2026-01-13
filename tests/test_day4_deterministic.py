import uuid
import pytest
from datetime import date
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.clustering import cluster_messages_v1

USER_ID = uuid.UUID("96cd6791-db08-4723-9b61-36377b9f6c9a")


@pytest.mark.asyncio
async def test_clustering_deterministic(async_session: AsyncSession):
    digest_date = date.fromisoformat("2026-01-12")

    # Run clustering first time
    await cluster_messages_v1(async_session, user_id=USER_ID, digest_date=digest_date)

    q = text("""
        SELECT c.title, count(*) AS n
        FROM clusters c
        JOIN messages m ON m.cluster_id = c.id
        WHERE c.user_id = :uid AND c.digest_date = :d
        GROUP BY c.title
        ORDER BY n DESC, c.title ASC
    """)

    rows1 = (await async_session.execute(q, {"uid": str(USER_ID), "d": digest_date})).all()

    # Re-run clustering
    await cluster_messages_v1(async_session, user_id=USER_ID, digest_date=digest_date)

    rows2 = (await async_session.execute(q, {"uid": str(USER_ID), "d": digest_date})).all()

    assert rows1 == rows2
