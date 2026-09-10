from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from app.core.runtime_contract import (
    EXPECTED_COMBINATION_MODEL_VERSION,
    runtime_revision,
)
from backend.api.schemas.jobs import (
    BatchJobCreate,
    HypothesisJobCreate,
    JudgmentJobCreate,
)
from backend.application.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from backend.application.queue import JobQueue
from backend.db.models import AnalysisJob

logger = logging.getLogger(__name__)


class JobWriter(Protocol):
    async def create(
        self,
        *,
        mode: str,
        request_payload: dict,
        name: str | None = None,
        retry_of_id: UUID | None = None,
    ) -> AnalysisJob: ...

    async def get(self, job_id: UUID) -> AnalysisJob | None: ...

    async def fail(
        self,
        job_id: UUID,
        *,
        code: str,
        message: str,
    ) -> AnalysisJob | None: ...


class JobService:
    def __init__(
        self,
        *,
        repository: JobWriter,
        queue: JobQueue,
        provider_available: Callable[[str, str | None], Awaitable[bool]] | None = None,
        model_used: Callable[[str, str | None], Awaitable[None]] | None = None,
        revision_provider: Callable[[], str] = runtime_revision,
        # Group-scoped variants receive (provider, model, api_group_id). When a
        # submitting user belongs to an ApiGroup these are used instead so the
        # availability gate and usage counters apply to the group's own
        # provider rows, never the global defaults.
        scope_provider_available: Callable[
            [str, str | None, str], Awaitable[bool]
        ] | None = None,
        scope_model_used: Callable[
            [str, str | None, str], Awaitable[None]
        ] | None = None,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._provider_available = provider_available
        self._model_used = model_used
        self._revision_provider = revision_provider
        self._scope_provider_available = scope_provider_available
        self._scope_model_used = scope_model_used

    def _with_runtime_contract(self, mode: str, payload: dict) -> dict:
        enriched = dict(payload)
        if mode in {"hypothesis", "batch"}:
            enriched["expected_model_version"] = (
                EXPECTED_COMBINATION_MODEL_VERSION
            )
            enriched["requested_at_revision"] = self._revision_provider()
        return enriched

    def _with_rotation_snapshot(self, payload: dict) -> dict:
        enabled = bool(payload.pop("rotation_enabled", False))
        candidates = payload.pop("rotation_candidates", None)
        if not enabled:
            return payload

        requested_provider = payload.get("provider") or "openai"
        requested_model = payload.get("model")
        normalized: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in candidates or []:
            provider = str(candidate.get("provider") or requested_provider)
            model = str(candidate.get("model") or requested_model or "")
            protocol = str(candidate.get("api_protocol") or "openai")
            revision = int(candidate.get("connection_revision") or 1)
            identity = (provider, protocol, model)
            if identity in seen:
                continue
            seen.add(identity)
            normalized.append(
                {
                    "provider": provider,
                    "api_protocol": protocol,
                    "model": model,
                    "connection_revision": revision,
                }
            )
        if not normalized:
            raise ServiceUnavailableError(
                code="ROTATION_CANDIDATES_REQUIRED",
                message="未提供可用的轮换模型",
                retryable=False,
            )
        payload["rotation_enabled"] = True
        payload["rotation_snapshot_version"] = 1
        payload["rotation_candidates"] = normalized
        return payload

    async def _submit(
        self,
        mode: str,
        payload: dict,
        *,
        name: str | None = None,
        retry_of_id: UUID | None = None,
    ) -> AnalysisJob:
        payload = self._with_runtime_contract(mode, payload)
        payload = self._with_rotation_snapshot(payload)
        scope = payload.get("api_group_id")
        gate = None
        if scope is not None and self._scope_provider_available is not None:
            gate = lambda provider, model: self._scope_provider_available(  # noqa: E731
                provider, model, str(scope)
            )
        elif self._provider_available is not None:
            gate = self._provider_available
        if gate is not None:
            targets = (
                payload.get("rotation_candidates") or []
                if payload.get("rotation_enabled")
                else [{"provider": payload.get("provider") or "openai", "model": payload.get("model")}]
            )
            for target in targets:
                provider = str(target.get("provider") or "openai")
                model = target.get("model")
                if not await gate(provider, model):
                    raise ServiceUnavailableError(
                    code="PROVIDER_MODEL_NOT_VERIFIED",
                    message="所选模型尚未通过当前连接验证或当前不可用",
                    retryable=False,
                )
        job = await self._repository.create(
            mode=mode,
            request_payload=payload,
            name=name,
            retry_of_id=retry_of_id,
        )
        try:
            await self._queue.enqueue("run_analysis_job", str(job.id))
        except Exception as error:
            await self._repository.fail(
                job.id,
                code="QUEUE_UNAVAILABLE",
                message="Task queue is unavailable",
            )
            raise ServiceUnavailableError(
                code="QUEUE_UNAVAILABLE",
                message="Task queue is unavailable",
            ) from error
        if self._model_used is not None:
            provider = payload.get("provider") or "openai"
            usage = None
            if scope is not None and self._scope_model_used is not None:
                usage = lambda p, m: self._scope_model_used(p, m, str(scope))  # noqa: E731
            else:
                usage = self._model_used
            try:
                await usage(provider, payload.get("model"))
            except Exception:
                logger.warning(
                    "Failed to record model usage for provider=%s model=%s",
                    provider,
                    payload.get("model"),
                    exc_info=True,
                )
        return job

    async def submit_hypothesis(
        self, request: HypothesisJobCreate, *, api_group_id: str | None = None
    ) -> AnalysisJob:
        payload = request.model_dump(exclude_none=True)
        if api_group_id:
            payload["api_group_id"] = api_group_id
        name = payload.pop("name", None)
        return await self._submit(mode="hypothesis", payload=payload, name=name)

    async def submit_judgment(
        self, request: JudgmentJobCreate, *, api_group_id: str | None = None
    ) -> AnalysisJob:
        payload = request.model_dump(exclude_none=True)
        if api_group_id:
            payload["api_group_id"] = api_group_id
        name = payload.pop("name", None)
        return await self._submit(mode="judgment", payload=payload, name=name)

    async def submit_batch(
        self, request: BatchJobCreate, *, api_group_id: str | None = None
    ) -> AnalysisJob:
        payload = request.model_dump(exclude_none=True)
        if api_group_id:
            payload["api_group_id"] = api_group_id
        name = payload.pop("name", None)
        return await self._submit(mode="batch", payload=payload, name=name)

    async def retry(self, job_id: UUID) -> AnalysisJob:
        original = await self._repository.get(job_id)
        if original is None:
            raise NotFoundError(message="Original analysis job was not found")
        if original.status not in {"failed", "interrupted"}:
            raise ConflictError(
                code="JOB_NOT_FAILED",
                message="Only failed or interrupted jobs can be retried",
            )
        payload = dict(original.request_payload)
        return await self._submit(
            mode=original.mode,
            payload=payload,
            retry_of_id=job_id,
        )


__all__ = ["JobService", "JobWriter"]
