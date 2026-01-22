# app/scripts/seed_dev.py
from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import User, Message, Channel, MessageStatus

DEMO_EMAIL = "demo@inboxsherpa.local"
DEMO_GMAIL = "demo@inboxsherpa.local"

# deterministic, won’t collide with a real user
TEST_USER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, DEMO_EMAIL)


def _db_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if not url:
        raise RuntimeError("Missing DATABASE_URL (or DB_URL) env var")
    return url


def _try_run_migrations() -> bool:
    """
    Best-effort: if Alembic is available in the container, run `alembic upgrade head`.
    Returns True if we *think* it ran, False otherwise.
    """
    # alembic.ini typically at repo root in container (/app)
    alembic_ini = os.path.exists("alembic.ini")
    if not alembic_ini:
        return False
    try:
        # Works if alembic is installed and configured
        subprocess.check_call(["alembic", "upgrade", "head"])
        return True
    except Exception:
        return False


async def seed_dev() -> None:
    engine = create_async_engine(_db_url(), future=True)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        try:
            # 1) Ensure the demo user exists
            user = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        except ProgrammingError as e:
            # Typically: relation "users" does not exist
            ran = _try_run_migrations()
            await engine.dispose()

            if ran:
                # If migrations ran, tell the caller to rerun seed_dev once
                raise RuntimeError(
                    "DB schema was missing; ran `alembic upgrade head`. "
                    "Please re-run: python -m app.scripts.seed_dev"
                ) from e

            raise RuntimeError(
                "DB schema is missing (tables not created). "
                "Run migrations first, then re-run seed_dev.\n\n"
                "If you use Alembic:\n"
                "  alembic upgrade head\n\n"
                "If you don't use Alembic yet, you need a table-creation step."
            ) from e

        if user is None:
            user = User(
                id=TEST_USER_ID,
                email=DEMO_EMAIL,
                gmail_account_email=DEMO_GMAIL,
                gmail_last_history_id=None,
            )
            session.add(user)
            await session.flush()

        # 2) Ensure there are messages for that user
        msg_count = await session.scalar(
            select(func.count(Message.id)).where(Message.user_id == user.id)
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
                        user_id=user.id,
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
    print(f"Seeded demo user: {user.id} {DEMO_EMAIL}")


if __name__ == "__main__":
    asyncio.run(seed_dev())
