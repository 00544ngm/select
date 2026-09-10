from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.complement_evidence import EvidenceStatus
from app.domain.dto import ProductDTO
from app.services.complement_evidence_service import ComplementEvidenceService


def _review(index: int) -> str:
    return f"Review {index}: I need another matching accessory to use this product properly."


@pytest.fixture
def llm():
    client = AsyncMock()
    client.chat_structured = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_no_reviews_returns_insufficient_without_calling_llm(llm):
    service = ComplementEvidenceService(llm)

    result = await service.analyze(
        ProductDTO(title="Main product"),
        ProductDTO(title="Candidate", url="https://www.walmart.com/ip/item/123"),
    )

    assert result.status is EvidenceStatus.INSUFFICIENT
    assert result.valid_review_count == 0
    assert result.relevant_review_count == 0
    llm.chat_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_uses_indexed_source_reviews_and_server_owned_original_text(llm):
    llm.chat_structured.return_value = {
        "reviews": [
            {
                "review_index": index,
                "is_relevant": index == 0,
                "translation_zh": "需要另一个配套附件。" if index == 0 else "无关",
                "keywords": ["matching accessory"] if index == 0 else [],
                "reason": "明确表达了配套需求" if index == 0 else "无关",
                "strength": "explicit" if index == 0 else "none",
            }
            for index in range(20)
        ]
    }
    reviews = [_review(index) for index in range(20)]
    service = ComplementEvidenceService(llm)

    result = await service.analyze(
        ProductDTO(title="Main product", description="Provides the matching accessory"),
        ProductDTO(
            title="Candidate",
            url="https://www.walmart.com/ip/item/123",
            review_snippets=reviews,
        ),
    )

    assert result.status is EvidenceStatus.SIGNAL
    assert result.valid_review_count == 20
    assert result.relevant_review_count == 1
    assert result.hit_rate == 0.05
    assert len(result.evidence) == 1
    assert result.evidence[0].original_text == reviews[0]
    assert result.evidence[0].translation_zh == "需要另一个配套附件。"
    assert result.evidence[0].source_url == "https://www.walmart.com/ip/item/123"

    messages = llm.chat_structured.await_args.kwargs["messages"]
    user_prompt = messages[1]["content"]
    assert '[0] "Review 0:' in user_prompt
    assert '[19] "Review 19:' in user_prompt
    assert "Main product" in user_prompt
    assert "Candidate" in user_prompt


@pytest.mark.asyncio
async def test_service_derives_verified_status_from_validated_hits(llm):
    llm.chat_structured.return_value = {
        "reviews": [
            {
                "review_index": index,
                "is_relevant": index < 3,
                "translation_zh": f"评论 {index}",
                "keywords": ["accessory"] if index < 3 else [],
                "reason": "明确互补" if index < 3 else "无关",
                "strength": "explicit" if index < 3 else "none",
            }
            for index in range(20)
        ]
    }
    service = ComplementEvidenceService(llm)

    result = await service.analyze(
        ProductDTO(title="A"),
        ProductDTO(title="B", review_snippets=[_review(index) for index in range(20)]),
    )

    assert result.status is EvidenceStatus.VERIFIED
    assert result.relevant_review_count == 3
    assert result.hit_rate == 0.15


@pytest.mark.asyncio
async def test_classification_failure_returns_analysis_failed_instead_of_raising(llm):
    llm.chat_structured.side_effect = RuntimeError("provider unavailable")
    service = ComplementEvidenceService(llm)

    result = await service.analyze(
        ProductDTO(title="A"),
        ProductDTO(title="B", review_snippets=[_review(index) for index in range(20)]),
    )

    assert result.status is EvidenceStatus.ANALYSIS_FAILED
    assert result.valid_review_count == 20
    assert result.relevant_review_count == 0
    assert result.failure_reason == "互补需求证据分析失败"


@pytest.mark.asyncio
async def test_incomplete_model_coverage_is_analysis_failed_not_not_found(llm):
    llm.chat_structured.return_value = {
        "reviews": [
            {
                "review_index": 0,
                "is_relevant": False,
                "translation_zh": "无关",
                "keywords": [],
                "reason": "无关",
                "strength": "none",
            }
        ]
    }
    service = ComplementEvidenceService(llm)

    result = await service.analyze(
        ProductDTO(title="A"),
        ProductDTO(title="B", review_snippets=[_review(index) for index in range(20)]),
    )

    assert result.status is EvidenceStatus.ANALYSIS_FAILED
    assert result.failure_reason == "互补需求证据分析失败"


@pytest.mark.asyncio
async def test_string_review_indexes_are_rejected_as_invalid_coverage(llm):
    llm.chat_structured.return_value = {
        "reviews": [
            {
                "review_index": str(index),
                "is_relevant": False,
                "translation_zh": "无关",
                "keywords": [],
                "reason": "无关",
                "strength": "none",
            }
            for index in range(20)
        ]
    }
    service = ComplementEvidenceService(llm)

    result = await service.analyze(
        ProductDTO(title="A"),
        ProductDTO(title="B", review_snippets=[_review(index) for index in range(20)]),
    )

    assert result.status is EvidenceStatus.ANALYSIS_FAILED
