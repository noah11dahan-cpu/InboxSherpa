import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.scripts.seed_dev import seed_dev

@pytest_asyncio.fixture
async def async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
@pytest_asyncio.fixture(scope="session", autouse=True)
async def _seed_database_once() -> None:
    # Ensures required user + messages exist for all tests after `down -v`
    await seed_dev()