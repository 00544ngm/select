from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from typing import Any

RESULT_WITH_CANDIDATES = "completed_with_qualified_candidates"
RESULT_NEEDS_EVIDENCE = "completed_needs_evidence"
RESULT_NO_CANDIDATES = "completed_no_qualified_candidates"
REQUIRED_SCORE_DIMENSIONS = {
    "function_necessity",
    "usage_continuity",
    "purchase_direction",
    "scene_fit",
    "enhancement_maintenance",
    "natural_copurchase",
}
REQUIRED_DECISION_FIELDS = (
    "primary_relation",
    "purchase_direction",
    "product_type_status",
    "evidence_level",
    "execution_status",
    "decision_action",
)
BLOCKED_GATE_CONTRACT = {
    "incompatible": ("compatibility_status", "incompatibility_reason"),
    "duplicate_function": ("duplication_status", "duplicate_function_reason"),
    "safety_blocked": ("safety_status", "safety_risk"),
}
FOOD_REJECTION_CODES = {"food_product", "ingestible_product", "confirmed_food"}
UNCERTAIN_REVIEW_STATUSES = {"likely_non_food", "needs_review"}


class ResultQualityError(RuntimeError):
    code = "RESULT_QUALITY_INVALID"
    retryable = False

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ResultSummary:
    result_status: str
    result_message: str
    raw_direction_count: int
    qualified_direction_count: int
    hold_direction_count: int
    rejected_direction_count: int
    rejection_summary: dict[str, int]


def summarize_directions(directions: list[dict[str, Any]]) -> ResultSummary:
    pass_count = sum(
        item.get("execution_status") == "pass"
        and _review_status(item) not in UNCERTAIN_REVIEW_STATUSES
        for item in directions
    )
    hold_count = sum(
        item.get("execution_status") == "hold"
        or (
            item.get("execution_status") == "pass"
            and _review_status(item) in UNCERTAIN_REVIEW_STATUSES
        )
        for item in directions
    )
    reject_count = sum(
        item.get("execution_status") == "reject" for item in directions
    )
    rejection_counts = Counter(
        code
        for item in directions
        if item.get("execution_status") == "reject"
        for code in item.get("rejection_codes", [])
    )
    if pass_count:
        status = RESULT_WITH_CANDIDATES
        message = (
            "分析已完成，发现达到高粘性门槛的候选，请按候选最终动作执行。"
        )
    elif hold_count:
        status = RESULT_NEEDS_EVIDENCE
        message = (
            "发现潜在方向，但当前不可执行，请先补齐兼容、安全或商品类型证据。"
        )
    else:
        status = RESULT_NO_CANDIDATES
        message = (
            "分析已完成，未发现达到高粘性门槛的辅品，不建议为了凑数量强行组合。"
        )
    return ResultSummary(
        result_status=status,
        result_message=message,
        raw_direction_count=len(directions),
        qualified_direction_count=pass_count,
        hold_direction_count=hold_count,
        rejected_direction_count=reject_count,
        rejection_summary=dict(sorted(rejection_counts.items())),
    )


def _fail(message: str) -> None:
    raise ResultQualityError(message)


def _review_status(direction: dict[str, Any]) -> str | None:
    review = direction.get("product_type_review")
    return review.get("status") if isinstance(review, dict) else None


def _has_located_evidence(review: dict[str, Any]) -> bool:
    evidence = review.get("evidence")
    return isinstance(evidence, list) and any(
        isinstance(item, dict)
        and isinstance(item.get("source_field"), str)
        and item["source_field"].strip()
        and isinstance(item.get("verbatim_quote"), str)
        and item["verbatim_quote"].strip()
        for item in evidence
    )


def _normalize_quote(value: Any) -> str:
    return " ".join(value.casefold().split()) if isinstance(value, str) else ""


def _has_anchored_direction_evidence(
    direction: dict[str, Any], review: dict[str, Any]
) -> bool:
    source_values = {
        "name_zh": direction.get("name"),
        "name_en": direction.get("name"),
        "canonical_name": direction.get("canonical_name"),
    }
    evidence = review.get("evidence")
    if not isinstance(evidence, list):
        return False
    for item in evidence:
        if not isinstance(item, dict) or item.get("source_field") not in source_values:
            continue
        quote = _normalize_quote(item.get("verbatim_quote"))
        source = _normalize_quote(source_values[item["source_field"]])
        if len(quote) >= 4 and "[truncated]" not in quote and quote in source:
            return True
    return False


def _validate_product_type_review(direction: dict[str, Any]) -> None:
    review = direction.get("product_type_review")
    if review is None:
        return
    if not isinstance(review, dict):
        _fail("Candidate product_type_review must be an object")
    required = ("status", "source", "confidence", "reason", "evidence", "action")
    if any(field not in review for field in required):
        _fail("Candidate product_type_review is incomplete")
    expected_actions = {
        "confirmed_food": "block",
        "confirmed_non_food": "continue",
        "likely_non_food": "continue_with_review",
        "needs_review": "continue_with_review",
    }
    status = review.get("status")
    if status in expected_actions and review.get("action") != expected_actions[status]:
        _fail("Candidate product_type_review status/action mismatch")
    if status in {"confirmed_food", "confirmed_non_food"} and not _has_located_evidence(
        review
    ):
        _fail("Confirmed product type review requires located evidence")
    if status in {"confirmed_food", "confirmed_non_food"} and not (
        _has_anchored_direction_evidence(direction, review)
    ):
        _fail("Confirmed product type review requires anchored evidence")
    if review.get("status") != "confirmed_food":
        return
    if direction.get("execution_status") != "reject":
        _fail("confirmed_food candidate must be rejected")
    rejection_codes = direction.get("rejection_codes")
    if not isinstance(rejection_codes, list) or not FOOD_REJECTION_CODES.intersection(
        rejection_codes
    ):
        _fail("confirmed_food candidate must carry a food rejection code")
    if not _has_located_evidence(review):
        _fail("confirmed_food candidate must carry located evidence")


def _validate_direction_shapes(
    directions: list[Any], *, model_name: str = "primary"
) -> None:
    rejection_patterns: list[tuple[str, ...]] = []
    for direction in directions:
        if not isinstance(direction, dict):
            _fail("Structured directions contain an invalid candidate")
        _validate_product_type_review(direction)
        if any(
            not isinstance(direction.get(field), str)
            or not direction[field].strip()
            for field in REQUIRED_DECISION_FIELDS
        ):
            _fail("Candidate decision fields must be non-empty strings")
        rejection_codes = direction.get("rejection_codes")
        if not isinstance(rejection_codes, list) or not all(
            isinstance(code, str) for code in rejection_codes
        ):
            _fail("Candidate rejection codes must be a list of strings")
        if direction.get("execution_status") == "reject" and not rejection_codes:
            _fail("Reject candidate must carry at least one rejection code")
        if direction.get("execution_status") != "reject" and rejection_codes:
            _fail("Non-reject candidate cannot carry rejection codes")
        score_breakdown = direction.get("score_breakdown")
        if not isinstance(score_breakdown, dict):
            _fail(f"{model_name} candidate score_breakdown is missing or invalid")
        missing_dimensions = sorted(REQUIRED_SCORE_DIMENSIONS - score_breakdown.keys())
        if missing_dimensions:
            _fail(
                f"{model_name} candidate is missing V2.1 score dimensions: "
                + ", ".join(missing_dimensions)
            )
        if any(
            isinstance(score_breakdown[field], bool)
            or not isinstance(score_breakdown[field], (int, float))
            or not isfinite(float(score_breakdown[field]))
            for field in REQUIRED_SCORE_DIMENSIONS
        ):
            _fail("Candidate score dimensions must be finite numbers")
        source_fact_ids = direction.get("source_fact_ids")
        if not isinstance(source_fact_ids, list) or not all(
            isinstance(item, str) and item.strip() for item in source_fact_ids
        ):
            _fail("Candidate source_fact_ids must be a list of non-empty strings")
        for code, (status_field, reason_field) in BLOCKED_GATE_CONTRACT.items():
            is_blocked = direction.get(status_field) == "blocked"
            has_code = code in rejection_codes
            if is_blocked != has_code:
                _fail(
                    f"{code} blocked gate status does not match rejection code"
                )
            if is_blocked and (
                not isinstance(direction.get(reason_field), str)
                or not direction[reason_field].strip()
                or not source_fact_ids
            ):
                _fail(f"{code} blocked gate lacks evidence")
        rejection_patterns.append(tuple(sorted(rejection_codes)))

    if (
        len(rejection_patterns) >= 8
        and len(set(rejection_patterns)) == 1
        and len(rejection_patterns[0]) >= 3
    ):
        _fail("suspicious rejection pattern")


def _validate_single_payload(
    payload: dict[str, Any], expected_model_version: str, *, model_name: str = "primary"
) -> None:
    if payload.get("model_version") != expected_model_version:
        _fail("Top-level model version does not match the requested contract")
    directions = payload.get("structured_directions")
    if not isinstance(directions, list):
        _fail("Structured directions are missing or invalid")
    if payload.get("directions_count") != len(directions):
        _fail("Direction count does not match structured directions")
    _validate_direction_shapes(directions, model_name=model_name)
    summary = summarize_directions(directions)
    expected_counts = {
        "raw_direction_count": summary.raw_direction_count,
        "qualified_direction_count": summary.qualified_direction_count,
        "hold_direction_count": summary.hold_direction_count,
        "rejected_direction_count": summary.rejected_direction_count,
    }
    for field, expected in expected_counts.items():
        if payload.get(field) != expected:
            _fail(f"{field} does not match structured directions")
    if payload.get("result_status") != summary.result_status:
        _fail("Result status does not match direction execution states")
    if payload.get("result_message") != summary.result_message:
        _fail("Result message does not match the computed result status")
    if payload.get("rejection_summary") != summary.rejection_summary:
        _fail("Rejection summary does not match direction rejection codes")

    for direction in directions:
        if direction.get("model_version") != expected_model_version:
            _fail("Candidate model version does not match the top-level contract")
        if direction.get("execution_status") not in {"pass", "hold", "reject"}:
            _fail("Candidate has an unknown execution status")
        if direction.get("execution_status") == "pass":
            if direction.get("purchase_direction") in {"reverse_dependency", "none"}:
                _fail("Pass candidate has an invalid purchase direction")
            if direction.get("primary_relation") in {"none", "weak_context"}:
                _fail("Pass candidate has no valid purchase-chain relation")
            if direction.get("product_type_status") != "non_food":
                _fail("Pass candidate must be verified as non-food")
            if direction.get("food_filter_status") != "allowed":
                _fail("Pass candidate must be allowed by the food filter")
            if direction["rejection_codes"]:
                _fail("Pass candidate cannot carry rejection codes")

    if not directions:
        if not payload.get("audit_performed"):
            _fail("Zero-direction result requires an omission audit")
        if payload.get("audit_reason") != "initial_v2.1_directions_empty":
            _fail("Zero-direction result requires an audit reason")
        if payload.get("initial_raw_direction_count") != 0:
            _fail("Zero-direction result requires an empty initial count")
        if payload.get("audit_raw_direction_count") != 0:
            _fail("Confirmed zero-direction result cannot contain audit directions")
        if payload.get("audit_outcome") != "confirmed_no_candidates":
            _fail("Zero-direction result requires a confirmed audit outcome")
    elif payload.get("audit_performed"):
        if payload.get("audit_reason") != "initial_v2.1_directions_empty":
            _fail("Recovered result requires an audit reason")
        if payload.get("initial_raw_direction_count") != 0:
            _fail("Recovered result requires an empty initial count")
        if not payload.get("audit_raw_direction_count"):
            _fail("Recovered result requires audit directions")
        if payload.get("audit_outcome") != "recovered_candidates":
            _fail("Recovered result requires a recovered audit outcome")


def validate_hypothesis_payload(
    payload: Any, *, expected_model_version: str | None
) -> None:
    if expected_model_version is None:
        return
    if not isinstance(payload, dict):
        _fail("Hypothesis result payload must be an object")
    if "models" in payload:
        models = payload["models"]
        if not isinstance(models, dict) or set(models) != {"gpt", "deepseek"}:
            _fail("Dual-model result must contain exactly gpt and deepseek")
        for model_name in ("gpt", "deepseek"):
            model_payload = models[model_name]
            if not isinstance(model_payload, dict):
                _fail("Dual-model result contains an invalid payload")
            _validate_single_payload(model_payload, expected_model_version, model_name=model_name)
    _validate_single_payload(payload, expected_model_version, model_name="primary")


def validate_batch_payload(
    payload: Any, *, expected_model_version: str | None
) -> None:
    if expected_model_version is None:
        return
    if not isinstance(payload, dict):
        _fail("Batch result payload must be an object")
    results = payload.get("results")
    if not isinstance(results, list):
        _fail("Batch results must be a list")
    for item in results:
        validate_hypothesis_payload(
            item,
            expected_model_version=expected_model_version,
        )


__all__ = [
    "RESULT_NEEDS_EVIDENCE",
    "RESULT_NO_CANDIDATES",
    "RESULT_WITH_CANDIDATES",
    "ResultQualityError",
    "ResultSummary",
    "summarize_directions",
    "validate_batch_payload",
    "validate_hypothesis_payload",
]
