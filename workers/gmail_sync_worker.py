from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone, date
from contextlib import asynccontextmanager

from sqlalchemy import select

from app.db.deps import get_session as get_session_dep
from app.models import User
from app.services.gmail_sync import sync_gmail_day


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else default


@asynccontextmanager
async def session_ctx():
    """
    get_session_dep() is an async generator (FastAPI dependency).
    This wrapper turns it into a proper async context manager for workers/scripts.
    """
    async for session in get_session_dep():
        try:
            yield session
        finally:
            # FastAPI deps usually handle cleanup, but being explicit is safe.
            await session.close()


async def run_once() -> None:
    tz_name = _env_str("SYNC_TZ", "America/Montreal")
    max_messages = _env_int("SYNC_MAX_MESSAGES", 500)

    # Pick a day to sync: default = today in UTC date (your sync_gmail_day converts using tz_name)
    # If you want "today local", keep using digest/today endpoint from API side.
    digest_date: date = datetime.now(timezone.utc).date()

    async with session_ctx() as session:
        # Sync for all users (simple first pass). If you only want users with tokens,
        # this is still fine because sync_gmail_day will raise "No Gmail token stored".
        users = (await session.execute(select(User.id))).scalars().all()

        for user_id in users:
            try:
                out = await sync_gmail_day(
                    session,
                    user_id=user_id,
                    digest_date=digest_date,
                    tz_name=tz_name,
                    max_messages=max_messages,
                )
                print(f"[worker] sync ok user={user_id} inserted={out.get('inserted')} deduped={out.get('deduped')}")
            except RuntimeError as e:
                # Common expected case if user hasn't connected Gmail yet
                msg = str(e)
                if "No Gmail token stored" in msg:
                    print(f"[worker] skip user={user_id} (no token)")
                    continue
                print(f"[worker] sync error user={user_id}: {e}")
            except Exception as e:
                print(f"[worker] unexpected error user={user_id}: {e}")


async def run_loop() -> None:
    sleep_s = _env_int("SYNC_SLEEP_SECONDS", 60)

    while True:
        await run_once()
        await asyncio.sleep(sleep_s)


if __name__ == "__main__":
    asyncio.run(run_loop())
