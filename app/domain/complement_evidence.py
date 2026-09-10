from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    SIGNAL = "signal"
    NOT_FOUND = "not_found"
    INSUFFICIENT = "insufficient"
    ANALYSIS_FAILED = "analysis_failed"


class EvidenceAnalysisState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class IndexedReview:
    index: int
    text: str


@dataclass(frozen=True)
class ComplementEvidenceHit:
    review_index: int
    original_text: str
    translation_zh: str = ""
    keywords: list[str] = field(default_factory=list)
    reason: str = ""
    strength: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_reviews(reviews: list[str]) -> list[IndexedReview]:
    normalized: list[IndexedReview] = []
    seen: set[str] = set()
    for raw in reviews:
        if not isinstance(raw, str):
            continue
        text = " ".join(raw.split())
        if len(text) < 20:
            continue
        dedupe_key = text.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(IndexedReview(index=len(normalized), text=text))
    return normalized


def validate_hits(
    raw_hits: list[dict[str, Any]],
    indexed_reviews: list[IndexedReview],
    *,
    source_url: str = "",
) -> list[ComplementEvidenceHit]:
    review_by_index = {review.index: review for review in indexed_reviews}
    accepted: list[ComplementEvidenceHit] = []
    seen_indexes: set[int] = set()

    for raw in raw_hits:
        if not isinstance(raw, dict) or raw.get("is_relevant") is not True:
            continue
        review_index = raw.get("review_index")
        if type(review_index) is not int:
            continue
        if review_index in seen_indexes or review_index not in review_by_index:
            continue
        seen_indexes.add(review_index)
        keywords = raw.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        accepted.append(
            ComplementEvidenceHit(
                review_index=review_index,
                original_text=review_by_index[review_index].text,
                translation_zh=str(raw.get("translation_zh", "") or ""),
                keywords=[str(keyword) for keyword in keywords if str(keyword).strip()],
                reason=str(raw.get("reason", "") or ""),
                strength=str(raw.get("strength", "") or ""),
                source_url=source_url,
            )
        )

    return accepted


def derive_evidence_status(
    *,
    valid_count: int,
    hit_count: int,
    explicit_hit_count: int | None = None,
    analysis_state: EvidenceAnalysisState,
) -> EvidenceStatus:
    if analysis_state is EvidenceAnalysisState.FAILED:
        return EvidenceStatus.ANALYSIS_FAILED
    if hit_count > 0:
        hit_rate = hit_count / valid_count if valid_count else 0
        explicit_count = hit_count if explicit_hit_count is None else explicit_hit_count
        if (
            valid_count >= 20
            and hit_count >= 3
            and hit_rate >= 0.10
            and explicit_count >= 2
        ):
            return EvidenceStatus.VERIFIED
        return EvidenceStatus.SIGNAL
    if valid_count >= 20:
        return EvidenceStatus.NOT_FOUND
    return EvidenceStatus.INSUFFICIENT


__all__ = [
    "ComplementEvidenceHit",
    "EvidenceAnalysisState",
    "EvidenceStatus",
    "IndexedReview",
    "derive_evidence_status",
    "normalize_reviews",
    "validate_hits",
]
