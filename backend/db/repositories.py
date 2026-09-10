from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import timezone
from typing import Any
from uuid import UUID

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.product_url import detect_product_platform
from backend.db.models import (
    AnalysisJob,
    Artifact,
    JobModelAttempt,
    JobProduct,
    ProductSnapshot,
    utc_now,
)


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        mode: str,
        request_payload: dict[str, Any],
        name: str | None = None,
        retry_of_id: UUID | None = None,
    ) -> AnalysisJob:
        job = AnalysisJob(
            mode=mode,
            status="queued",
            name=name,
            request_payload=request_payload,
            retry_of_id=retry_of_id,
        )
        self._session.add(job)
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def get(self, job_id: UUID) -> AnalysisJob | None:
        return await self._session.get(AnalysisJob, job_id)

    async def create_product_snapshot(
        self, job_id: UUID, product: Any, *, role: str, position: int
    ) -> ProductSnapshot:
        data = asdict(product) if is_dataclass(product) else dict(product)
        snapshot = ProductSnapshot(
            product_url=str(data.get("url") or ""),
            platform=detect_product_platform(str(data.get("url") or "")),
            scraped_data=data,
        )
        self._session.add(snapshot)
        await self._session.flush()
        self._session.add(
            JobProduct(
                job_id=job_id,
                product_snapshot_id=snapshot.id,
                role=role,
                position=position,
            )
        )
        await self._session.commit()
        await self._session.refresh(snapshot)
        return snapshot

    async def list_job_products(
        self, job_id: UUID
    ) -> list[tuple[JobProduct, ProductSnapshot]]:
        result = await self._session.execute(
            select(JobProduct, ProductSnapshot)
            .join(
                ProductSnapshot,
                ProductSnapshot.id == JobProduct.product_snapshot_id,
            )
            .where(JobProduct.job_id == job_id)
            .order_by(JobProduct.position.asc())
        )
        return list(result.all())

    async def create_attempt(
        self,
        job_id: UUID,
        *,
        ordinal: int,
        provider: str,
        api_protocol: str,
        model: str,
    ) -> JobModelAttempt:
        attempt = JobModelAttempt(
            job_id=job_id,
            ordinal=ordinal,
            provider=provider,
            api_protocol=api_protocol,
            model=model,
            status="running",
        )
        self._session.add(attempt)
        await self._session.commit()
        await self._session.refresh(attempt)
        return attempt

    async def finish_attempt(
        self,
        attempt_id: UUID,
        *,
        status: str,
        stage: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> JobModelAttempt | None:
        attempt = await self._session.get(JobModelAttempt, attempt_id)
        if attempt is None:
            return None

        finished_at = utc_now()
        started_at = attempt.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        attempt.status = status
        attempt.stage = stage
        attempt.error_code = error_code
        attempt.error_message = error_message
        attempt.finished_at = finished_at
        attempt.duration_ms = max(
            0,
            int((finished_at - started_at).total_seconds() * 1000),
        )
        await self._session.commit()
        await self._session.refresh(attempt)
        return attempt

    async def delete_attempt(self, attempt_id: UUID) -> None:
        await self._session.execute(
            delete(JobModelAttempt).where(JobModelAttempt.id == attempt_id)
        )
        await self._session.commit()

    async def list_attempts(self, job_id: UUID) -> list[JobModelAttempt]:
        result = await self._session.execute(
            select(JobModelAttempt)
            .where(JobModelAttempt.job_id == job_id)
            .order_by(JobModelAttempt.ordinal.asc())
        )
        return list(result.scalars().all())

    async def rename(self, job_id: UUID, name: str | None) -> AnalysisJob | None:
        statement = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(name=name, version=AnalysisJob.version + 1)
            .returning(AnalysisJob)
        )
        result = await self._session.execute(statement)
        job = result.scalar_one_or_none()
        await self._session.commit()
        if job is not None:
            await self._session.refresh(job)
        return job

    async def transition(
        self,
        job_id: UUID,
        *,
        expected: str,
        target: str,
    ) -> AnalysisJob | None:
        statement = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.status == expected)
            .values(status=target, version=AnalysisJob.version + 1)
            .returning(AnalysisJob)
        )
        result = await self._session.execute(statement)
        job = result.scalar_one_or_none()
        await self._session.commit()
        return job

    async def fail(
        self,
        job_id: UUID,
        *,
        code: str,
        message: str,
    ) -> AnalysisJob | None:
        statement = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(
                status="failed",
                error_code=code,
                error_message=message,
                version=AnalysisJob.version + 1,
            )
            .returning(AnalysisJob)
        )
        result = await self._session.execute(statement)
        job = result.scalar_one_or_none()
        await self._session.commit()
        return job

    async def set_runtime_notice(
        self,
        job_id: UUID,
        *,
        code: str | None,
        message: str | None,
    ) -> AnalysisJob | None:
        statement = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status == "running",
            )
            .values(
                error_code=code,
                error_message=message,
                version=AnalysisJob.version + 1,
            )
            .returning(AnalysisJob)
        )
        result = await self._session.execute(statement)
        job = result.scalar_one_or_none()
        await self._session.commit()
        if job is not None:
            await self._session.refresh(job)
        return job

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        mode: str | None = None,
        status: str | None = None,
    ) -> tuple[list[AnalysisJob], int]:
        conditions = []
        if mode is not None:
            conditions.append(AnalysisJob.mode == mode)
        if status is not None:
            conditions.append(AnalysisJob.status == status)

        count_statement = select(func.count()).select_from(AnalysisJob)
        if conditions:
            count_statement = count_statement.where(*conditions)
        total_result = await self._session.execute(count_statement)
        total = total_result.scalar_one()

        query = (
            select(AnalysisJob)
            .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if conditions:
            query = query.where(*conditions)
        result = await self._session.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def complete(
        self,
        job_id: UUID,
        *,
        result_payload: dict[str, Any] | None = None,
    ) -> AnalysisJob | None:
        statement = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(
                status="completed",
                result_payload=result_payload,
                progress=100,
                version=AnalysisJob.version + 1,
            )
            .returning(AnalysisJob)
        )
        result = await self._session.execute(statement)
        job = result.scalar_one_or_none()
        await self._session.commit()
        return job

    async def set_progress(self, job_id: UUID, pct: int) -> AnalysisJob | None:
        bounded = max(0, min(100, int(pct)))
        statement = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.status == "running")
            .values(
                progress=case(
                    (AnalysisJob.progress < bounded, bounded),
                    else_=AnalysisJob.progress,
                ),
                version=AnalysisJob.version + 1,
            )
            .returning(AnalysisJob)
        )
        result = await self._session.execute(statement)
        job = result.scalar_one_or_none()
        await self._session.commit()
        return job

    async def update_result_payload(
        self,
        job_id: UUID,
        *,
        result_payload: dict[str, Any],
    ) -> AnalysisJob | None:
        statement = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(
                result_payload=result_payload,
                version=AnalysisJob.version + 1,
            )
            .returning(AnalysisJob)
        )
        result = await self._session.execute(statement)
        job = result.scalar_one_or_none()
        await self._session.commit()
        return job

    async def get_artifact(self, job_id: UUID, kind: str) -> Artifact | None:
        statement = select(Artifact).where(
            Artifact.job_id == job_id, Artifact.kind == kind
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


__all__ = ["JobRepository"]
