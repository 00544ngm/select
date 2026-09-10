from __future__ import annotations

import pytest

from app.domain.complement_evidence import (
    EvidenceAnalysisState,
    EvidenceStatus,
    derive_evidence_status,
    normalize_reviews,
    validate_hits,
)


def _reviews(count: int) -> list[str]:
    return [f"Review {index}: this is a useful customer comment." for index in range(count)]


@pytest.mark.parametrize(
    ("valid_count", "hit_count", "expected"),
    [
        (9, 0, EvidenceStatus.INSUFFICIENT),
        (9, 2, EvidenceStatus.SIGNAL),
        (10, 0, EvidenceStatus.INSUFFICIENT),
        (10, 1, EvidenceStatus.SIGNAL),
        (19, 0, EvidenceStatus.INSUFFICIENT),
        (19, 2, EvidenceStatus.SIGNAL),
        (20, 0, EvidenceStatus.NOT_FOUND),
        (20, 1, EvidenceStatus.SIGNAL),
        (20, 2, EvidenceStatus.SIGNAL),
        (20, 3, EvidenceStatus.VERIFIED),
        (40, 3, EvidenceStatus.SIGNAL),
        (40, 4, EvidenceStatus.VERIFIED),
    ],
)
def test_status_thresholds(valid_count: int, hit_count: int, expected: EvidenceStatus):
    assert (
        derive_evidence_status(
            valid_count=valid_count,
            hit_count=hit_count,
            analysis_state=EvidenceAnalysisState.COMPLETED,
        )
        == expected
    )


def test_failed_analysis_is_not_misreported_as_not_found():
    assert (
        derive_evidence_status(
            valid_count=30,
            hit_count=0,
            analysis_state=EvidenceAnalysisState.FAILED,
        )
        == EvidenceStatus.ANALYSIS_FAILED
    )


def test_verified_requires_two_explicit_hits():
    assert (
        derive_evidence_status(
            valid_count=20,
            hit_count=3,
            explicit_hit_count=1,
            analysis_state=EvidenceAnalysisState.COMPLETED,
        )
        == EvidenceStatus.SIGNAL
    )


def test_normalize_reviews_removes_blanks_short_text_and_duplicates():
    reviews = normalize_reviews(
        [
            "",
            "too short",
            "  This customer review is long enough to retain.  ",
            "This customer review is long enough to retain.",
            "A different customer review with useful detail.",
        ]
    )

    assert [review.index for review in reviews] == [0, 1]
    assert [review.text for review in reviews] == [
        "This customer review is long enough to retain.",
        "A different customer review with useful detail.",
    ]


def test_validate_hits_rejects_unknown_duplicate_and_non_relevant_indexes():
    indexed = normalize_reviews(_reviews(3))
    raw_hits = [
        {"review_index": 0, "is_relevant": True, "reason": "explicit need"},
        {"review_index": 0, "is_relevant": True, "reason": "duplicate"},
        {"review_index": 2, "is_relevant": False, "reason": "not relevant"},
        {"review_index": 99, "is_relevant": True, "reason": "fabricated"},
        {"review_index": "1", "is_relevant": True, "reason": "wrong type"},
    ]

    hits = validate_hits(raw_hits, indexed)

    assert len(hits) == 1
    assert hits[0].review_index == 0
    assert hits[0].original_text == indexed[0].text
    assert hits[0].reason == "explicit need"
