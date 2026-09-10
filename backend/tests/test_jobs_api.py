from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from backend.api.dependencies import (
    get_job_queue,
    get_job_repository,
    get_job_service,
    get_provider_repository,
)
from backend.api.schemas.jobs import JobNameUpdate
from backend.application.errors import ConflictError, NotFoundError
from backend.api.dependencies import get_api_group_repository
from backend.config import BackendSettings, get_backend_settings
from backend.main import create_app
from backend.security.auth import get_current_user


def job_stub(
    status: str = "queued",
    mode: str = "hypothesis",
    result_payload=None,
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        name=None,
        mode=mode,
        status=status,
        progress=0,
        error_code=None,
        error_message=None,
        retry_of_id=None,
        request_payload={"url": "https://www.walmart.com/ip/example/12345"},
        result_payload=result_payload,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_submit_hypothesis_returns_accepted_job():
    service = AsyncMock()
    service.submit_hypothesis.return_value = job_stub()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/jobs/hypothesis",
            json={"url": "https://www.walmart.com/ip/example/12345"},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    service.submit_hypothesis.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_missing_job_returns_not_found():
    repository = AsyncMock()
    repository.get.return_value = None
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "method", "body", "service_method", "mode"),
    [
        (
            "/api/v1/jobs/judgment",
            "post",
            {
                "a_url": "https://www.walmart.com/ip/example/12345",
                "b_urls": ["https://www.amazon.com/dp/B000000001"],
            },
            "submit_judgment",
            "judgment",
        ),
        (
            "/api/v1/jobs/batch",
            "post",
            {"urls": ["https://www.walmart.com/ip/example/12345"]},
            "submit_batch",
            "batch",
        ),
    ],
)
async def test_submit_other_job_modes(path, method, body, service_method, mode):
    service = AsyncMock()
    getattr(service, service_method).return_value = job_stub(mode=mode)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await getattr(client, method)(path, json=body)

    assert response.status_code == 202
    assert response.json()["mode"] == mode


@pytest.mark.asyncio
async def test_list_jobs_returns_paginated_response():
    repository = AsyncMock()
    repository.list.return_value = ([job_stub()], 1)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs?page=1&page_size=20")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1


@pytest.mark.asyncio
async def test_list_jobs_serializes_interrupted_job_with_other_statuses():
    repository = AsyncMock()
    repository.list.return_value = (
        [
            job_stub(status="completed"),
            job_stub(status="failed"),
            job_stub(status="interrupted"),
        ],
        3,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs?page=1&page_size=20")

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["items"]] == [
        "completed",
        "failed",
        "interrupted",
    ]


@pytest.mark.asyncio
async def test_list_jobs_includes_product_and_top_direction_highlights():
    repository = AsyncMock()
    repository.list.return_value = (
        [
            job_stub(
                status="completed",
                result_payload={
                    "product_title": "Pizza Cutter",
                    "product_images": ["https://images.example/main.jpg"],
                    "structured_directions": [
                        {
                            "name": "Non-Slip Mat",
                            "score": 91,
                            "type": "低成本附加",
                            "keywords": {
                                "amazon": "pizza cutting board non slip"
                            },
                        }
                    ],
                },
            )
        ],
        1,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs")

    item = response.json()["items"][0]
    assert item["product_title"] == "Pizza Cutter"
    assert item["product_image"] == "https://images.example/main.jpg"
    assert item["top_direction_name"] == "Non-Slip Mat"
    assert item["top_direction_score"] == 91
    assert item["top_direction_keywords"] == {
        "amazon": "pizza cutting board non slip"
    }


@pytest.mark.asyncio
async def test_list_jobs_keeps_empty_highlights_for_old_failed_job():
    repository = AsyncMock()
    repository.list.return_value = ([job_stub(status="failed")], 1)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["product_title"] is None
    assert item["top_direction_name"] is None
    assert item["top_direction_keywords"] == {}


@pytest.mark.asyncio
async def test_retry_failed_job_returns_new_accepted_job():
    service = AsyncMock()
    service.retry.return_value = job_stub()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_service] = lambda: service
    job_id = uuid4()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/jobs/{job_id}/retry")

    assert response.status_code == 202
    service.retry.assert_awaited_once_with(job_id)


@pytest.mark.asyncio
async def test_result_requires_completed_job():
    repository = AsyncMock()
    repository.get.return_value = job_stub(status="running")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}/result")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_completed_result_is_returned():
    repository = AsyncMock()
    repository.get.return_value = job_stub(
        status="completed",
        result_payload={"final_grade": "A"},
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}/result")

    assert response.status_code == 200
    assert response.json() == {"final_grade": "A"}


@pytest.mark.asyncio
async def test_artifact_download_uses_registered_safe_path(tmp_path):
    artifact_file = tmp_path / "result.json"
    artifact_file.write_text('{"ok": true}', encoding="utf-8")
    repository = AsyncMock()
    repository.get_artifact.return_value = SimpleNamespace(path=str(artifact_file))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository
    app.dependency_overrides[get_backend_settings] = lambda: BackendSettings(
        artifact_dir=tmp_path
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}/artifacts/json")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_cross_review_accepts_two_tested_provider_models():
    repository = AsyncMock()
    repository.get.return_value = job_stub(status="completed", result_payload={"models": {"gpt": {}, "deepseek": {}}})
    repository.update_result_payload.return_value = None
    provider_repository = AsyncMock()
    provider_repository.get.side_effect = [
        SimpleNamespace(is_enabled=True, encrypted_api_key="cipher", last_test_status="success", supported_models=["model-a"], api_protocol="openai", display_name="A"),
        SimpleNamespace(is_enabled=True, encrypted_api_key="cipher", last_test_status="success", supported_models=["model-b"], api_protocol="anthropic", display_name="B"),
    ]
    provider_repository.list_model_validations.side_effect = [
        [SimpleNamespace(api_protocol="openai", model="model-a", status="verified", tested_at=datetime.now(timezone.utc))],
        [SimpleNamespace(api_protocol="anthropic", model="model-b", status="verified", tested_at=datetime.now(timezone.utc))],
    ]
    queue = AsyncMock()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository
    app.dependency_overrides[get_provider_repository] = lambda: provider_repository
    app.dependency_overrides[get_job_queue] = lambda: queue

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/jobs/{uuid4()}/cross-review", json={"reviewer_a": {"provider": "custom", "model": "model-a"}, "reviewer_b": {"provider": "openai", "model": "model-b"}})

    assert response.status_code == 202
    queue.enqueue.assert_awaited_once()
    payload = repository.update_result_payload.await_args.kwargs["result_payload"]
    assert payload["cross_review"]["status"] == "queued"
    assert payload["cross_review"]["reviewers"][0]["model"] == "model-a"


@pytest.mark.asyncio
async def test_cross_review_accepts_old_verification_for_current_connection():
    repository = AsyncMock()
    repository.get.return_value = job_stub(status="completed", result_payload={"models": {"gpt": {}, "deepseek": {}}})
    provider_repository = AsyncMock()
    provider_repository.get.return_value = SimpleNamespace(
        is_enabled=True,
        encrypted_api_key="cipher",
        api_protocol="openai",
        display_name="A",
        validation_revision=4,
    )
    provider_repository.list_model_validations.side_effect = [
        [SimpleNamespace(
            api_protocol="openai", model="model-a", status="verified",
            tested_at=datetime.now(timezone.utc) - timedelta(days=30),
            connection_revision=4, is_selected=True,
        )],
        [SimpleNamespace(
            api_protocol="openai", model="model-b", status="verified",
            tested_at=datetime.now(timezone.utc) - timedelta(days=30),
            connection_revision=4, is_selected=True,
        )],
    ]
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository
    app.dependency_overrides[get_provider_repository] = lambda: provider_repository
    app.dependency_overrides[get_job_queue] = lambda: AsyncMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/jobs/{uuid4()}/cross-review",
            json={
                "reviewer_a": {"provider": "custom", "model": "model-a"},
                "reviewer_b": {"provider": "openai", "model": "model-b"},
            },
        )

    assert response.status_code == 202


def test_job_name_update_normalizes_whitespace_and_rejects_long_names():
    assert JobNameUpdate(name="  采购复核  ").name == "采购复核"
    assert JobNameUpdate(name="   ").name is None
    with pytest.raises(ValidationError):
        JobNameUpdate(name="名" * 101)


@pytest.mark.asyncio
async def test_rename_job_updates_name():
    job_id = uuid4()
    renamed = job_stub()
    renamed.id = job_id
    renamed.name = "采购复核"
    repository = AsyncMock()
    repository.rename.return_value = renamed
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/jobs/{job_id}/name",
            json={"name": "  采购复核  "},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "采购复核"
    repository.rename.assert_awaited_once_with(job_id, "采购复核")


@pytest.mark.asyncio
async def test_rename_job_returns_not_found():
    repository = AsyncMock()
    repository.rename.return_value = None
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/jobs/{uuid4()}/name",
            json={"name": None},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_review_rejects_same_model_identity():
    repository = AsyncMock()
    repository.get.return_value = job_stub(status="completed", result_payload={"models": {"gpt": {}, "deepseek": {}}})
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository
    app.dependency_overrides[get_provider_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_queue] = lambda: AsyncMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/jobs/{uuid4()}/cross-review", json={"reviewer_a": {"provider": "custom", "model": "same"}, "reviewer_b": {"provider": "custom", "model": "same"}})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CROSS_REVIEW_DUPLICATE_MODEL"


@pytest.mark.asyncio
async def test_retry_missing_job_returns_not_found():
    service = AsyncMock()
    service.retry.side_effect = NotFoundError(message="not found")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/jobs/{uuid4()}/retry")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_non_failed_job_returns_conflict():
    service = AsyncMock()
    service.retry.side_effect = ConflictError(
        code="JOB_NOT_FAILED", message="not failed"
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/jobs/{uuid4()}/retry")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_retry_links_new_job_to_original():
    service = AsyncMock()
    original_id = uuid4()
    new_job = job_stub()
    new_job.retry_of_id = original_id
    service.retry.return_value = new_job
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/jobs/{original_id}/retry")

    assert response.status_code == 202
    assert response.json()["retry_of_id"] == str(original_id)


@pytest.mark.asyncio
async def test_artifact_missing_record_returns_not_found():
    repository = AsyncMock()
    repository.get_artifact.return_value = None
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}/artifacts/json")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_artifact_path_escape_returns_not_found(tmp_path):
    artifact_file = tmp_path / "result.json"
    artifact_file.write_text("{}", encoding="utf-8")
    repository = AsyncMock()
    repository.get_artifact.return_value = SimpleNamespace(path=str(artifact_file))
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository
    safe_dir = tmp_path / "safe"
    safe_dir.mkdir()
    app.dependency_overrides[get_backend_settings] = lambda: BackendSettings(
        artifact_dir=safe_dir
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}/artifacts/json")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_artifact_missing_file_returns_not_found(tmp_path):
    repository = AsyncMock()
    repository.get_artifact.return_value = SimpleNamespace(
        path=str(tmp_path / "nonexistent.json")
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository
    app.dependency_overrides[get_backend_settings] = lambda: BackendSettings(
        artifact_dir=tmp_path
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}/artifacts/json")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_artifact_invalid_kind_returns_not_found():
    repository = AsyncMock()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/jobs/{uuid4()}/artifacts/pdf")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_forwards_mode_and_status_filters():
    repository = AsyncMock()
    repository.list.return_value = ([job_stub(mode="judgment")], 1)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/jobs?page=1&page_size=20&mode=judgment&status=completed"
        )

    assert response.status_code == 200
    repository.list.assert_awaited_once_with(
        page=1, page_size=20, mode="judgment", status="completed"
    )


@pytest.mark.asyncio
async def test_list_jobs_validates_page_parameters():
    repository = AsyncMock()
    repository.list.return_value = ([], 0)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_api_group_repository] = lambda: AsyncMock()
    app.dependency_overrides[get_job_repository] = lambda: repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/jobs?page=0&page_size=200")

    assert response.status_code == 422
