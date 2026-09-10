from __future__ import annotations

from typing import Protocol

from arq.connections import ArqRedis

from backend.application.local_queue import LocalQueueRepository


class JobQueue(Protocol):
    async def enqueue(self, function: str, *args: str) -> None: ...


class ArqJobQueue:
    def __init__(self, redis: ArqRedis) -> None:
        self._redis = redis

    async def enqueue(self, function: str, *args: str) -> None:
        job = await self._redis.enqueue_job(function, *args)
        if job is None:
            raise RuntimeError("ARQ rejected the job")


class SqliteJobQueue:
    _SUPPORTED_FUNCTIONS = frozenset({"run_analysis_job", "run_cross_review"})

    def __init__(self, repository: LocalQueueRepository) -> None:
        self._repository = repository

    async def enqueue(self, function: str, *args: str) -> None:
        if function not in self._SUPPORTED_FUNCTIONS:
            raise ValueError("Unsupported local queue function")
        await self._repository.enqueue(function, *args)


__all__ = ["ArqJobQueue", "JobQueue", "SqliteJobQueue"]
