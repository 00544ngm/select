from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.config import database_connection_url, get_backend_settings
from backend.db.engine import create_database_engine

settings = get_backend_settings()
engine = create_database_engine(database_connection_url(settings))


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


SessionFactory = create_session_factory(engine)


async def get_session() -> AsyncSession:
    async with SessionFactory() as session:
        yield session


__all__ = [
    "SessionFactory",
    "create_session_factory",
    "engine",
    "get_session",
]
