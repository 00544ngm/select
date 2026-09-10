from __future__ import annotations

from datetime import timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import AnalysisJob, JobModelAttempt, LocalQueueItem, utc_now


async def recover_interrupted_jobs(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        running_attempts = await session.execute(
            select(JobModelAttempt).where(
                JobModelAttempt.status == "running",
                JobModelAttempt.job_id.in_(
                    select(AnalysisJob.id).where(AnalysisJob.status == "running")
                ),
            )
        )
        attempts = list(running_attempts.scalars().all())
        finished_at = utc_now()
        jobs = await session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.status == "running")
            .values(
                status="interrupted",
                error_code="APP_INTERRUPTED",
                error_message="软件上次运行被中断，请手动重新提交",
                version=AnalysisJob.version + 1,
            )
        )
        for attempt in attempts:
            started_at = attempt.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            attempt.status = "failed"
            attempt.stage = "recovery"
            attempt.error_code = "APP_INTERRUPTED"
            attempt.error_message = "软件上次运行被中断"
            attempt.finished_at = finished_at
            attempt.duration_ms = max(
                0,
                int((finished_at - started_at).total_seconds() * 1000),
            )
        await session.execute(
            update(LocalQueueItem)
            .where(LocalQueueItem.status == "running")
            .values(status="interrupted")
        )
        await session.commit()
        return int(jobs.rowcount or 0)


__all__ = ["recover_interrupted_jobs"]
