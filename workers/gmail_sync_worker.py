import asyncio
import os
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import GmailToken
from app.services.gmail_sync import sync_gmail_inbox


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return int(v)


async def main() -> None:
    interval = _env_int("GMAIL_SYNC_INTERVAL_SECONDS", 120)
    max_msgs = _env_int("GMAIL_SYNC_MAX_MESSAGES", 50)

    while True:
        try:
            async with AsyncSessionLocal() as session:
                user_ids = list(
                    (await session.scalars(select(GmailToken.user_id))).all()
                )

                for uid in user_ids:
                    try:
                        out = await sync_gmail_inbox(session, user_id=uid, max_messages=max_msgs)
                        print(f"[worker] gmail sync user={uid} {out}")
                    except Exception as e:
                        print(f"[worker] gmail sync failed user={uid}: {e}")
        except Exception as e:
            print(f"[worker] loop error: {e}")

        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())