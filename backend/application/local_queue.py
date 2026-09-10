from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import LocalQueueItem
from backend.desktop.backup import database_write_guard


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LocalQueueRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        live_database: Path | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._live_database = live_database

    def _write_guard(self):
        if self._live_database is None:
            return nullcontext()
        return database_write_guard(self._live_database)

    async def enqueue(self, function: str, *arguments: str) -> LocalQueueItem:
        item = LocalQueueItem(function=function, arguments=list(arguments))
        with self._write_guard():
            async with self._session_factory() as session:
                session.add(item)
                await session.commit()
                await session.refresh(item)
        return item

    async def claim_next(self, worker_id: str) -> LocalQueueItem | None:
        with self._write_guard():
            async with self._session_factory() as session:
                candidate = await session.scalar(
                    select(LocalQueueItem.id)
                    .where(LocalQueueItem.status == "queued")
                    .order_by(LocalQueueItem.created_at, LocalQueueItem.id)
                    .limit(1)
                )
                if candidate is None:
                    return None
                statement = (
                    update(LocalQueueItem)
                    .where(
                        LocalQueueItem.id == candidate,
                        LocalQueueItem.status == "queued",
                    )
                    .values(
                        status="running",
                        claimed_by=worker_id,
                        heartbeat_at=utc_now(),
                        started_at=utc_now(),
                        attempts=LocalQueueItem.attempts + 1,
                    )
                    .returning(LocalQueueItem)
                )
                result = await session.execute(statement)
                item = result.scalar_one_or_none()
                await session.commit()
                return item

    async def complete(self, item_id: UUID) -> LocalQueueItem | None:
        return await self._finish(item_id, status="completed")

    async def fail(self, item_id: UUID) -> LocalQueueItem | None:
        return await self._finish(item_id, status="failed")

    async def _finish(self, item_id: UUID, *, status: str) -> LocalQueueItem | None:
        with self._write_guard():
            async with self._session_factory() as session:
                result = await session.execute(
                    update(LocalQueueItem)
                    .where(
                        LocalQueueItem.id == item_id,
                        LocalQueueItem.status == "running",
                    )
                    .values(status=status, finished_at=utc_now())
                    .returning(LocalQueueItem)
                )
                item = result.scalar_one_or_none()
                await session.commit()
                return item

    async def request_cancel(self, item_id: UUID) -> LocalQueueItem | None:
        with self._write_guard():
            async with self._session_factory() as session:
                result = await session.execute(
                    update(LocalQueueItem)
                    .where(
                        LocalQueueItem.id == item_id,
                        LocalQueueItem.status.in_(("queued", "running")),
                    )
                    .values(
                        cancel_requested=True,
                        status="cancelled",
                        finished_at=utc_now(),
                    )
                    .returning(LocalQueueItem)
                )
                item = result.scalar_one_or_none()
                await session.commit()
                return item


__all__ = ["LocalQueueRepository"]
