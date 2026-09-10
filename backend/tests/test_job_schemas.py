from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.api.schemas.jobs import (
    BatchJobCreate,
    HypothesisJobCreate,
    JudgmentJobCreate,
)


VALID_A_URL = "https://www.walmart.com/ip/example/12345"


def test_hypothesis_request_rejects_lookalike_host():
    with pytest.raises(ValidationError, match="Unsupported platform"):
        HypothesisJobCreate(url="https://walmart.com.evil.example/ip/12345")


def test_judgment_requires_at_least_one_b_url():
    with pytest.raises(ValidationError):
        JudgmentJobCreate(a_url=VALID_A_URL, b_urls=[])


def test_judgment_validates_every_b_url():
    with pytest.raises(ValidationError, match="Unsupported platform"):
        JudgmentJobCreate(
            a_url=VALID_A_URL,
            b_urls=["https://amazon.com.evil.example/dp/B000000001"],
        )


def test_batch_request_deduplicates_urls_without_reordering():
    request = BatchJobCreate(
        urls=[
            VALID_A_URL,
            " https://www.amazon.com/dp/B000000001 ",
            VALID_A_URL,
        ]
    )

    assert request.urls == [
        VALID_A_URL,
        "https://www.amazon.com/dp/B000000001",
    ]
