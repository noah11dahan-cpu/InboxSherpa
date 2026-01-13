import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


@pytest_asyncio.fixture
async def async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
