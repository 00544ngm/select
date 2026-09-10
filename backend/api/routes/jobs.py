from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from backend.api.dependencies import (
    get_api_group_repository,
    get_job_queue,
    get_job_repository,
    get_job_service,
    get_provider_repository,
)
from backend.db.auth_repository import ApiGroupRepository
from backend.db.models import User
from backend.api.schemas.jobs import (
    BatchJobCreate,
    CrossReviewCreate,
    HypothesisJobCreate,
    JobAttemptResponse,
    JobDetail,
    JobListResponse,
    JobNameUpdate,
    JobRotationSnapshot,
    JobSummary,
    JudgmentJobCreate,
)
from backend.application.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from backend.application.job_service import JobService
from backend.application.queue import JobQueue
from backend.application.result_highlights import extract_result_highlights
from backend.config import BackendSettings, get_backend_settings
from backend.db.provider_repository import (
    GroupProviderRepository,
    ProviderConfigurationRepository,
)
from backend.db.repositories import JobRepository
from backend.security.auth import get_current_user

MEDIA_TYPES = {
    "json": "application/json",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json_deepseek": "application/json",
    "excel_deepseek": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Server (web) mode: job data/submission requires a valid login. In desktop
# mode get_current_user short-circuits to None before any DB/token work, so the
# single-user desktop app is unaffected (its jobs stay gated by the desktop
# session token middleware instead).
router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(get_current_user)],
)


async def _submitter_scope(
    user: User | None,
    groups: ApiGroupRepository,
) -> str | None:
    """Resolve the effective ApiGroup scope for the authenticated submitter.

    Returns None for the global default set (desktop single-user, or a logged-in
    user not assigned to any group). A group that is missing or disabled rejects
    the submission outright.
    """
    if user is None or user.api_group_id is None:
        return None
    group = await groups.get(user.api_group_id)
    if group is None or group.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "GROUP_NOT_AVAILABLE",
                "message": "所属接口分组不存在或已停用，请联系管理员",
                "retryable": False,
            },
        )
    return str(user.api_group_id)


@router.post(
    "/hypothesis",
    response_model=JobSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_hypothesis(
    request: HypothesisJobCreate,
    service: JobService = Depends(get_job_service),
    user: User | None = Depends(get_current_user),
    groups: ApiGroupRepository = Depends(get_api_group_repository),
) -> JobSummary:
    scope = await _submitter_scope(user, groups)
    try:
        job = await service.submit_hypothesis(request, api_group_id=scope)
    except ServiceUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error
    return JobSummary.model_validate(job)


@router.post(
    "/judgment",
    response_model=JobSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_judgment(
    request: JudgmentJobCreate,
    service: JobService = Depends(get_job_service),
    user: User | None = Depends(get_current_user),
    groups: ApiGroupRepository = Depends(get_api_group_repository),
) -> JobSummary:
    scope = await _submitter_scope(user, groups)
    try:
        job = await service.submit_judgment(request, api_group_id=scope)
    except ServiceUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error
    return JobSummary.model_validate(job)


@router.post(
    "/batch",
    response_model=JobSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_batch(
    request: BatchJobCreate,
    service: JobService = Depends(get_job_service),
    user: User | None = Depends(get_current_user),
    groups: ApiGroupRepository = Depends(get_api_group_repository),
) -> JobSummary:
    scope = await _submitter_scope(user, groups)
    try:
        job = await service.submit_batch(request, api_group_id=scope)
    except ServiceUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error
    return JobSummary.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    mode: str | None = Query(None),
    status: str | None = Query(None),
    repository: JobRepository = Depends(get_job_repository),
) -> JobListResponse:
    items, total = await repository.list(
        page=page, page_size=page_size, mode=mode, status=status
    )

    def _summary_with_highlights(item: object) -> JobSummary:
        summary = JobSummary.model_validate(item)
        request_payload = getattr(item, "request_payload", {})
        result_payload = getattr(item, "result_payload", None)
        if isinstance(request_payload, dict):
            summary.rotation_enabled = bool(request_payload.get("rotation_enabled", False))
        if isinstance(result_payload, dict):
            successful_model = result_payload.get("successful_model")
            if isinstance(successful_model, str) and successful_model:
                summary.successful_model = successful_model
        if isinstance(result_payload, dict):
            grade = result_payload.get("grade")
            score = result_payload.get("score")
            # Dual-model payloads keep top-level keys from the primary model;
            # fall back to models.gpt just in case.
            if grade is None or score is None:
                models = result_payload.get("models")
                if isinstance(models, dict):
                    primary = models.get("gpt")
                    if isinstance(primary, dict):
                        grade = grade if grade is not None else primary.get("grade")
                        score = score if score is not None else primary.get("score")
            if isinstance(grade, str) and grade:
                summary.grade = grade
            if isinstance(score, (int, float)):
                summary.score = float(score)
        for field, value in extract_result_highlights(result_payload).items():
            setattr(summary, field, value)
        return summary

    return JobListResponse(
        items=[_summary_with_highlights(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: UUID,
    repository: JobRepository = Depends(get_job_repository),
) -> JobDetail:
    job = await repository.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "Analysis job was not found",
                "retryable": False,
            },
        )
    detail = JobDetail.model_validate(job)
    request_payload = job.request_payload if isinstance(job.request_payload, dict) else {}
    detail.rotation = JobRotationSnapshot(
        enabled=bool(request_payload.get("rotation_enabled", False)),
        candidates=request_payload.get("rotation_candidates") or [],
        snapshot_version=request_payload.get("rotation_snapshot_version"),
    )
    attempts = await repository.list_attempts(job_id)
    if not isinstance(attempts, list):
        attempts = []
    detail.attempts = [JobAttemptResponse.model_validate(item) for item in attempts]
    detail.attempt_count = len(detail.attempts)
    if isinstance(job.result_payload, dict):
        successful_model = job.result_payload.get("successful_model")
        if isinstance(successful_model, str) and successful_model:
            detail.successful_model = successful_model
    return detail


@router.get("/{job_id}/attempts", response_model=list[JobAttemptResponse])
async def list_job_attempts(
    job_id: UUID,
    repository: JobRepository = Depends(get_job_repository),
) -> list[JobAttemptResponse]:
    if await repository.get(job_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "Analysis job was not found",
                "retryable": False,
            },
        )
    attempts = await repository.list_attempts(job_id)
    if not isinstance(attempts, list):
        attempts = []
    return [JobAttemptResponse.model_validate(item) for item in attempts]


@router.patch("/{job_id}/name", response_model=JobSummary)
async def rename_job(
    job_id: UUID,
    request: JobNameUpdate,
    repository: JobRepository = Depends(get_job_repository),
) -> JobSummary:
    job = await repository.rename(job_id, request.name)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "Analysis job was not found",
                "retryable": False,
            },
        )
    return JobSummary.model_validate(job)


@router.post(
    "/{job_id}/retry",
    response_model=JobSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> JobSummary:
    try:
        job = await service.retry(job_id)
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error
    except ConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error
    except ServiceUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            },
        ) from error
    return JobSummary.model_validate(job)


@router.get("/{job_id}/result", response_model=None)
async def get_job_result(
    job_id: UUID,
    repository: JobRepository = Depends(get_job_repository),
):
    job = await repository.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "Analysis job was not found",
                "retryable": False,
            },
        )
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOB_NOT_COMPLETED",
                "message": "Analysis job has not completed yet",
                "retryable": False,
            },
        )
    if job.result_payload is None:
        return {}
    return dict(job.result_payload)


@router.post(
    "/{job_id}/cross-review",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_cross_review(
    job_id: UUID,
    request: CrossReviewCreate,
    repository: JobRepository = Depends(get_job_repository),
    queue: JobQueue = Depends(get_job_queue),
    provider_repository: ProviderConfigurationRepository = Depends(get_provider_repository),
) -> dict:
    """Trigger cross-review using two explicitly selected tested models."""
    job = await repository.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job not found", "retryable": False},
        )
    # Cross-review must resolve reviewers against the SAME provider scope the
    # original job ran under (its ApiGroup if any, else the global set).
    request_payload = job.request_payload if isinstance(job.request_payload, dict) else {}
    job_scope = request_payload.get("api_group_id")
    if job_scope:
        provider_repository = GroupProviderRepository(
            provider_repository.session, api_group_id=UUID(job_scope)
        )
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOB_NOT_COMPLETED", "message": "Job must be completed", "retryable": False},
        )
    payload = job.result_payload or {}
    models = payload.get("models")
    if not models or len(models) < 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "NOT_DUAL_MODEL", "message": "Job does not have dual model results", "retryable": False},
        )
    existing_review = payload.get("cross_review") or {}
    if existing_review.get("status") in {"queued", "running", "completed"} or payload.get("cross_review") and "status" not in existing_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CROSS_REVIEW_EXISTS", "message": "Cross-review already completed", "retryable": False},
        )

    if request.reviewer_a == request.reviewer_b:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "CROSS_REVIEW_DUPLICATE_MODEL", "message": "Review models must be different", "retryable": False})

    selections = []
    for selected in (request.reviewer_a, request.reviewer_b):
        record = await provider_repository.get(selected.provider)
        if record is None or not record.is_enabled or not record.encrypted_api_key:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "CROSS_REVIEW_PROVIDER_UNAVAILABLE", "message": "Selected provider is not enabled or configured", "retryable": False})
        validations = await provider_repository.list_model_validations(selected.provider)
        verified = False
        for validation in validations:
            if (
                validation.api_protocol == record.api_protocol
                and validation.model == selected.model
                and validation.status == "verified"
                and bool(getattr(validation, "is_selected", True))
                and int(getattr(validation, "connection_revision", 1))
                == int(getattr(record, "validation_revision", 1))
            ):
                verified = True
                break
        if not verified:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "CROSS_REVIEW_MODEL_NOT_VERIFIED", "message": "所选模型尚未通过当前连接验证或未勾选使用", "retryable": False})
        selections.append({"provider": selected.provider, "model": selected.model, "api_protocol": record.api_protocol, "display_name": record.display_name})

    await repository.update_result_payload(job_id, result_payload={**payload, "cross_review": {"status": "queued", "reviewers": selections}})
    await queue.enqueue("run_cross_review", str(job_id))
    return {"status": "queued", "job_id": str(job_id)}


@router.get("/{job_id}/artifacts/{kind}")
async def download_artifact(
    job_id: UUID,
    kind: str,
    repository: JobRepository = Depends(get_job_repository),
    settings: BackendSettings = Depends(get_backend_settings),
) -> FileResponse:
    if kind not in MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact kind '{kind}' is not supported",
                "retryable": False,
            },
        )

    artifact = await repository.get_artifact(job_id, kind)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": "Artifact was not found for this job",
                "retryable": False,
            },
        )

    artifact_path = Path(artifact.path).resolve()
    resolved_artifact_dir = settings.artifact_dir.resolve()

    try:
        artifact_path.relative_to(resolved_artifact_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": "Artifact path is invalid",
                "retryable": False,
            },
        )

    if not artifact_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": "Artifact file was not found on disk",
                "retryable": False,
            },
        )

    ext = kind.split("_")[0]
    filename = f"{job_id}_{kind}.{ext}"
    return FileResponse(
        path=artifact_path,
        media_type=MEDIA_TYPES[kind],
        filename=filename,
    )


__all__ = ["router"]
