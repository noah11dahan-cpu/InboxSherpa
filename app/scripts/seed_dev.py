import asyncio
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import User

DEMO_EMAIL = "demo@inboxsherpa.local"

async def main() -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing:
            print(f"Demo user already exists: {existing.id} {existing.email}")
            return

        user = User(email=DEMO_EMAIL, gmail_account_email=DEMO_EMAIL)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"Created demo user: {user.id} {user.email}")

if __name__ == "__main__":
    asyncio.run(main())
