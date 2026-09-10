from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.stickiness import EvidenceLevel

_STOPWORDS = {
    "and", "for", "the", "with", "set", "of", "to", "a", "an", "in",
}
_BUNDLE_WORDS = {
    "bundle", "kit", "with", "compatible", "replacement", "refill", "accessory",
}


@dataclass(frozen=True)
class EvidenceRecord:
    source_type: str
    source_owner: str
    platform: str
    url: str
    query: str
    excerpt: str
    verified_at: str
    status: str = "completed"
    stance: str = "supports_discovery"
    failure_reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class MarketEvidenceRecord:
    level: EvidenceLevel
    platform: str
    query: str
    verified_at: str
    status: str
    raw_results: tuple[dict[str, str], ...] = ()
    matched_results: tuple[dict[str, str], ...] = ()
    matched_count: int = 0
    bundle_count: int = 0
    failure_reason: str = ""
    records: tuple[EvidenceRecord, ...] = ()

    @property
    def source_urls(self) -> tuple[str, ...]:
        return tuple(item.get("url", "") for item in self.matched_results if item.get("url"))

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "platform": self.platform,
            "query": self.query,
            "verified_at": self.verified_at,
            "status": self.status,
            "raw_results": list(self.raw_results),
            "matched_results": list(self.matched_results),
            "matched_count": self.matched_count,
            "bundle_count": self.bundle_count,
            "source_urls": list(self.source_urls),
            "failure_reason": self.failure_reason,
            "records": [record.to_dict() for record in self.records],
        }


def classify_market_results(
    results: list[dict[str, str]],
    primary_terms: list[str],
    candidate_terms: list[str],
    *,
    query: str,
    verified_at: str | None = None,
) -> MarketEvidenceRecord:
    timestamp = verified_at or datetime.now(timezone.utc).isoformat()
    unique: dict[str, dict[str, str]] = {}
    for item in results:
        url = str(item.get("url", "")).strip()
        if url and url not in unique:
            unique[url] = {key: str(value) for key, value in item.items()}
    primary = _term_tokens(primary_terms)
    candidate = _term_tokens(candidate_terms)
    matched: list[dict[str, str]] = []
    bundles: list[dict[str, str]] = []
    for item in unique.values():
        title_tokens = _term_tokens([item.get("title", "")])
        if primary and candidate and primary & title_tokens and candidate & title_tokens:
            matched.append(item)
            if _BUNDLE_WORDS & title_tokens:
                bundles.append(item)
    level = derive_market_level(matched, len(matched), len(bundles))
    records = tuple(
        EvidenceRecord(
            source_type="candidate_discovery",
            source_owner="Walmart search",
            platform="Walmart",
            url=item.get("url", ""),
            query=query,
            excerpt=item.get("title", ""),
            verified_at=timestamp,
        )
        for item in matched
    )
    return MarketEvidenceRecord(
        level=level,
        platform="Walmart",
        query=query,
        verified_at=timestamp,
        status="completed",
        raw_results=tuple(unique.values()),
        matched_results=tuple(matched),
        matched_count=len(matched),
        bundle_count=len(bundles),
        records=records,
    )


def derive_market_level(
    results: list[dict[str, str]], matched_count: int, bundle_count: int
) -> EvidenceLevel:
    if not results or matched_count <= 0:
        return EvidenceLevel.E0
    return EvidenceLevel.E1


def failed_market_evidence(query: str, reason: str, *, verified_at: str | None = None) -> MarketEvidenceRecord:
    return MarketEvidenceRecord(
        level=EvidenceLevel.E0,
        platform="Walmart",
        query=query,
        verified_at=verified_at or datetime.now(timezone.utc).isoformat(),
        status="failed",
        failure_reason=reason,
    )


def _term_tokens(values: list[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for token in re.findall(r"[a-z0-9]+", value.casefold()):
            if token not in _STOPWORDS and len(token) >= 3:
                tokens.add(token)
    return tokens


__all__ = [
    "EvidenceRecord",
    "MarketEvidenceRecord",
    "classify_market_results",
    "derive_market_level",
    "failed_market_evidence",
]
