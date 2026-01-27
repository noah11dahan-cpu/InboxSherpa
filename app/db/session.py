# app/db/session.py
from __future__ import annotations

import os
import sys
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL (or DB_URL) is not set")

# IMPORTANT:
# When pytest is running, disable pooling to prevent asyncpg loop-crossing errors.
IS_PYTEST = "pytest" in sys.modules

engine_kwargs: dict = {
    "future": True,
    "echo": False,
}

if IS_PYTEST:
    engine_kwargs["poolclass"] = NullPool

engine: AsyncEngine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
