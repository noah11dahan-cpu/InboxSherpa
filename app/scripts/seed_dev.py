from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import User, Message, Channel, MessageStatus

# This MUST match the USER_ID used in your tests (see failure trace)
TEST_USER_ID = uuid.UUID("96cd6791-db08-4723-9b61-36377b9f6c9a")

DEMO_EMAIL = "demo@inboxsherpa.local"
DEMO_GMAIL = "demo@inboxsherpa.local"


def _db_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if not url:
        raise RuntimeError("Missing DATABASE_URL (or DB_URL) env var")
    return url


async def seed_dev() -> None:
    engine = create_async_engine(_db_url(), future=True)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        # 1) Ensure the demo user exists WITH THE TEST UUID
        existing = await session.scalar(select(User).where(User.email == DEMO_EMAIL))

        if existing is not None and existing.id != TEST_USER_ID:
            # delete the "wrong-id" demo user so we can recreate with the test UUID
            await session.delete(existing)
            await session.flush()

        user = await session.get(User, TEST_USER_ID)
        if user is None:
            user = User(
                id=TEST_USER_ID,
                email=DEMO_EMAIL,
                gmail_account_email=DEMO_GMAIL,
                gmail_last_history_id=None,
            )
            session.add(user)
            await session.flush()

        # 2) Ensure there are messages for that user (so clustering can create clusters)
        msg_count = await session.scalar(
            select(func.count(Message.id)).where(Message.user_id == TEST_USER_ID)
        )
        if (msg_count or 0) == 0:
            now = datetime.now(timezone.utc)

            samples = [
                ("m-001", "School: Quiz tomorrow", "teacher@school.org", "quiz tomorrow on chapter 5"),
                ("m-002", "Work: PR review needed", "teammate@company.com", "can you review my PR?"),
                ("m-003", "Bills: Invoice due", "billing@service.com", "your invoice is due next week"),
                ("m-004", "Promos: 30% off sale", "store@shop.com", "unsubscribe | limited time offer"),
                ("m-005", "Social: Party invite", "friend@social.com", "rsvp for saturday night"),
            ]

            for ext_id, subject, sender, snippet in samples:
                session.add(
                    Message(
                        user_id=TEST_USER_ID,
                        thread_id=None,
                        cluster_id=None,
                        channel=Channel.json,
                        external_id=ext_id,
                        thread_external_id=None,
                        timestamp=now,
                        sender=sender,
                        subject=subject,
                        snippet=snippet,
                        body_text=snippet,
                        body_html=None,
                        labels=None,
                        history_id=None,
                        status=MessageStatus.inbox,
                        raw_payload=None,
                    )
                )

        await session.commit()

    await engine.dispose()
    print(f"Seeded demo user: {TEST_USER_ID} {DEMO_EMAIL}")


if __name__ == "__main__":
    asyncio.run(seed_dev())
