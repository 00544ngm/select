from __future__ import annotations

import pytest

from backend.application.job_recovery import recover_interrupted_jobs
from backend.db.engine import create_database_engine
from backend.db.models import AnalysisJob, JobModelAttempt
from backend.db.session import create_session_factory
from backend.desktop.migrations import upgrade_database_async


@pytest.mark.asyncio
async def test_startup_marks_running_job_interrupted_without_touching_completed(tmp_path) -> None:
    database = tmp_path / "recovery.db"
    url = f"sqlite+aiosqlite:///{database.as_posix()}"
    await upgrade_database_async(url)
    engine = create_database_engine(url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            running = AnalysisJob(mode="hypothesis", status="running", request_payload={})
            completed = AnalysisJob(mode="hypothesis", status="completed", request_payload={})
            session.add_all((running, completed))
            await session.commit()
            running_id, completed_id = running.id, completed.id

        assert await recover_interrupted_jobs(factory) == 1

        async with factory() as session:
            recovered = await session.get(AnalysisJob, running_id)
            untouched = await session.get(AnalysisJob, completed_id)
        assert recovered is not None
        assert recovered.status == "interrupted"
        assert recovered.error_code == "APP_INTERRUPTED"
        assert untouched is not None
        assert untouched.status == "completed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_startup_closes_running_model_attempt(tmp_path) -> None:
    database = tmp_path / "recovery-attempt.db"
    url = f"sqlite+aiosqlite:///{database.as_posix()}"
    await upgrade_database_async(url)
    engine = create_database_engine(url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            job = AnalysisJob(
                mode="hypothesis",
                status="running",
                request_payload={},
            )
            session.add(job)
            await session.flush()
            attempt = JobModelAttempt(
                job_id=job.id,
                ordinal=1,
                provider="openai",
                api_protocol="openai",
                model="gpt-5.6",
                status="running",
            )
            session.add(attempt)
            await session.commit()
            attempt_id = attempt.id

        assert await recover_interrupted_jobs(factory) == 1

        async with factory() as session:
            recovered_attempt = await session.get(JobModelAttempt, attempt_id)
        assert recovered_attempt is not None
        assert recovered_attempt.status == "failed"
        assert recovered_attempt.stage == "recovery"
        assert recovered_attempt.error_code == "APP_INTERRUPTED"
    finally:
        await engine.dispose()
