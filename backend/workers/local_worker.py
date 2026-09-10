from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from backend.application.local_queue import LocalQueueRepository
from backend.config import database_connection_url, get_backend_settings
from backend.db.session import SessionFactory
from backend.desktop.paths import DesktopPaths
from backend.workers.jobs import run_analysis_job, run_cross_review
from backend.workers.local_identity import write_local_worker_identity

Handler = Callable[..., Awaitable[object]]

HANDLERS: Mapping[str, Handler] = {
    "run_analysis_job": run_analysis_job,
    "run_cross_review": run_cross_review,
}


class LocalWorker:
    def __init__(
        self,
        repository: LocalQueueRepository,
        handlers: Mapping[str, Handler],
        *,
        worker_id: str | None = None,
    ) -> None:
        self._repository = repository
        self._handlers = handlers
        self.worker_id = worker_id or f"desktop-{uuid4()}"

    async def run_once(self) -> bool:
        item = await self._repository.claim_next(self.worker_id)
        if item is None:
            return False
        try:
            handler = self._handlers.get(item.function)
            if handler is None:
                raise LookupError("unsupported local queue function")
            await handler({}, *item.arguments)
        except BaseException:  # noqa: BLE001 - every worker termination is persisted
            await self._repository.fail(item.id)
        else:
            await self._repository.complete(item.id)
        return True

    async def run_forever(
        self,
        stop_event: asyncio.Event,
        *,
        idle_interval: float = 0.5,
        heartbeat_file: Path | None = None,
    ) -> None:
        while not stop_event.is_set():
            if heartbeat_file is not None:
                write_local_worker_identity(heartbeat_file, self.worker_id)
            handled = await self.run_once()
            if handled:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=idle_interval)
            except TimeoutError:
                pass


def _repository_from_settings() -> LocalQueueRepository:
    settings = get_backend_settings()
    if settings.runtime_mode != "desktop":
        raise RuntimeError("Local worker requires desktop runtime mode")
    database = database_connection_url(settings).database
    if not database:
        raise RuntimeError("Desktop SQLite database path is missing")
    return LocalQueueRepository(SessionFactory, live_database=Path(database))


async def _run() -> None:
    stop_event = asyncio.Event()
    worker = LocalWorker(
        _repository_from_settings(),
        HANDLERS,
        worker_id=os.environ.get("DESKTOP_WORKER_ID"),
    )
    heartbeat = os.environ.get("DESKTOP_WORKER_HEARTBEAT")
    heartbeat_file = (
        Path(heartbeat)
        if heartbeat
        else DesktopPaths.for_current_user().worker_heartbeat_file
    )
    await worker.run_forever(
        stop_event,
        heartbeat_file=heartbeat_file,
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()


__all__ = ["HANDLERS", "LocalWorker", "main"]
