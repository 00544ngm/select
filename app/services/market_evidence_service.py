from __future__ import annotations

from typing import Any

from app.core.logger import logger

from app.domain.dto import HypothesisResultDTO
from app.domain.market_evidence import (
    MarketEvidenceRecord,
    classify_market_results,
    failed_market_evidence,
)
from app.domain.stickiness import (
    EvidenceLevel,
    GateSignals,
    ScoreRatings,
    compute_stickiness,
)


class MarketEvidenceService:
    """Bounded, conservative Walmart evidence verification for V2 candidates."""

    def __init__(self) -> None:
        self._cache: dict[str, MarketEvidenceRecord] = {}

    async def verify_result(self, result: HypothesisResultDTO, browser: Any) -> dict[str, MarketEvidenceRecord]:
        primary_terms = list(result.product_profile.get("primary_search_terms", []))[:2]
        candidates = [
            direction for direction in result.directions
            if not direction.hypothesis.rejected and direction.hypothesis.raw_score >= 70
        ][:5]
        records: dict[str, MarketEvidenceRecord] = {}
        for direction in candidates:
            hypothesis = direction.hypothesis
            candidate_terms = [
                hypothesis.keywords.get("amazon", ""),
                hypothesis.keywords.get("en", ""),
                hypothesis.canonical_name,
            ]
            record = await self.verify_candidate(browser, primary_terms, candidate_terms)
            records[hypothesis.direction_name] = record
            try:
                current_level = EvidenceLevel(hypothesis.evidence_level)
            except ValueError:
                current_level = EvidenceLevel.E0
            if _evidence_rank(record.level) > _evidence_rank(current_level):
                _apply_record(hypothesis, record)
            else:
                _attach_record(hypothesis, record)
        result.directions.sort(key=lambda item: (-item.hypothesis.final_score, item.hypothesis.rejected, item.hypothesis.direction_name))
        return records

    async def verify_candidate(
        self,
        browser: Any,
        primary_terms: list[str],
        candidate_terms: list[str],
    ) -> MarketEvidenceRecord:
        query = " ".join([*primary_terms[:2], *candidate_terms[:2]]).strip()
        if not query:
            return failed_market_evidence("", "no search terms")
        key = " ".join(query.casefold().split())
        if key in self._cache:
            return self._cache[key]
        page = await browser.new_page()
        try:
            from app.infrastructure.walmart.search import search_walmart_page

            results = await search_walmart_page(page, query)
            record = classify_market_results(results, primary_terms, candidate_terms, query=query)
        except Exception as error:  # noqa: BLE001 - network/browser errors are evidence failures
            record = failed_market_evidence(query, str(error))
        finally:
            try:
                await page.close()
            except Exception as error:  # noqa: BLE001 - preserve evidence failure
                logger.warning(
                    "Market evidence page cleanup failed: {}",
                    type(error).__name__,
                )
        self._cache[key] = record
        return record


__all__ = ["MarketEvidenceService"]


def _evidence_rank(level: EvidenceLevel) -> int:
    return list(EvidenceLevel).index(level)


def _apply_record(hypothesis: Any, record: MarketEvidenceRecord) -> None:
    ratings = ScoreRatings(**hypothesis.score_inputs)
    gates = GateSignals(
        included="included_item" in hypothesis.rejection_codes,
        incompatible=getattr(hypothesis, "compatibility_status", "")
        == "blocked",
        compatibility_unverified=getattr(
            hypothesis, "compatibility_status", "needs_verification"
        )
        == "needs_verification",
        duplicate_function=getattr(hypothesis, "duplication_status", "")
        == "blocked",
        duplication_unverified=getattr(
            hypothesis, "duplication_status", "needs_verification"
        )
        == "needs_verification",
        no_valid_relation="no_valid_relation" in hypothesis.rejection_codes,
        safety_blocked=getattr(hypothesis, "safety_status", "") == "blocked",
        safety_unverified=getattr(
            hypothesis, "safety_status", "needs_verification"
        )
        == "needs_verification",
        category_or_scene_only=hypothesis.primary_relation == "weak_context",
        food_blocked=getattr(hypothesis, "product_type_status", "")
        in {"ingestible", "food"},
        needs_verification=getattr(hypothesis, "product_type_status", "")
        == "unknown",
        product_type_status=getattr(hypothesis, "product_type_status", "unknown"),
    )
    decision = compute_stickiness(ratings, record.level, gates)
    hypothesis.evidence_level = record.level.value
    hypothesis.score_breakdown = dict(decision.breakdown)
    hypothesis.raw_score = decision.raw_score
    hypothesis.score_cap = decision.score_cap
    hypothesis.final_score = decision.final_score
    hypothesis.estimated_score = decision.final_score
    hypothesis.recommendation_level = decision.recommendation
    hypothesis.rejected = decision.rejected
    hypothesis.rejection_codes = list(decision.rejection_codes)
    hypothesis.stickiness = _legacy_stickiness_label(decision.recommendation)
    hypothesis.evidence = {
        **hypothesis.evidence,
        "level": record.level.value,
        "market": record.to_dict(),
    }


def _attach_record(hypothesis: Any, record: MarketEvidenceRecord) -> None:
    """Persist failed or non-promoting evidence without changing the score cap."""
    hypothesis.evidence = {
        **hypothesis.evidence,
        "market": record.to_dict(),
    }


def _legacy_stickiness_label(recommendation: str) -> str:
    if recommendation in {"focus", "test_pool"}:
        return "high"
    if recommendation == "observe":
        return "medium"
    return "low"
