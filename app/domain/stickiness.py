from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TypeVar, overload

from app.domain.pairing_policy import (
    DecisionAction,
    ExecutionStatus,
    ProductTypeStatus,
    PurchaseDirection,
)


class EvidenceLevel(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"


@dataclass(frozen=True, init=False)
class ScoreRatings:
    """V2.1 six-dimensional ratings with compatibility for V2.0 inputs."""

    function_necessity: int
    usage_continuity: int
    purchase_direction: int
    scene_fit: int
    enhancement_maintenance: int
    natural_copurchase: int
    _legacy_mode: bool = field(default=False, repr=False, compare=False)
    _v21_mode: bool = field(default=False, repr=False, compare=False)
    _legacy_values: tuple[int, ...] = field(default=(), repr=False, compare=False)

    @overload
    def __init__(self, *values: int) -> None: ...

    @overload
    def __init__(
        self,
        *,
        function_necessity: int = 0,
        usage_continuity: int = 0,
        purchase_direction: int | None = None,
        scene_fit: int = 0,
        enhancement_maintenance: int = 0,
        natural_copurchase: int = 0,
        relation_strength: int | None = None,
        lifecycle_connection: int | None = None,
        repeat_value: int | None = None,
        function_gain: int | None = None,
        mental_copurchase: int | None = None,
        user_scene: int | None = None,
    ) -> None: ...

    def __init__(self, *values: int, **kwargs: int | None) -> None:
        legacy_values: tuple[int, ...] = ()
        if values:
            if len(values) != 6:
                raise TypeError("legacy ScoreRatings requires six positional values")
            kwargs = {
                "relation_strength": values[0],
                "lifecycle_connection": values[1],
                "repeat_value": values[2],
                "function_gain": values[3],
                "mental_copurchase": values[4],
                "user_scene": values[5],
                **kwargs,
            }
            legacy_values = tuple(int(value) for value in values)
            legacy_mode = True
            v21_mode = False
        else:
            legacy_mode = any(
                kwargs.get(key) is not None
                for key in (
                    "relation_strength",
                    "lifecycle_connection",
                    "repeat_value",
                    "function_gain",
                    "mental_copurchase",
                    "user_scene",
                )
            ) and not any(
                kwargs.get(key) is not None
                for key in (
                    "function_necessity",
                    "usage_continuity",
                    "scene_fit",
                    "enhancement_maintenance",
                    "natural_copurchase",
                )
            )
            if legacy_mode:
                legacy_values = tuple(
                    int(kwargs.get(key) or 0)
                    for key in (
                        "relation_strength",
                        "lifecycle_connection",
                        "repeat_value",
                        "function_gain",
                        "mental_copurchase",
                        "user_scene",
                    )
                )
            v21_mode = kwargs.get("purchase_direction") is not None
        object.__setattr__(
            self,
            "function_necessity",
            _rating_value(kwargs, "function_necessity", "relation_strength"),
        )
        object.__setattr__(
            self,
            "usage_continuity",
            _rating_value(kwargs, "usage_continuity", "lifecycle_connection"),
        )
        object.__setattr__(
            self,
            "purchase_direction",
            _rating_value(kwargs, "purchase_direction"),
        )
        object.__setattr__(self, "scene_fit", _rating_value(kwargs, "scene_fit", "user_scene"))
        object.__setattr__(
            self,
            "enhancement_maintenance",
            _rating_value(
                kwargs, "enhancement_maintenance", "function_gain", "repeat_value"
            ),
        )
        object.__setattr__(
            self,
            "natural_copurchase",
            _rating_value(kwargs, "natural_copurchase", "mental_copurchase"),
        )
        object.__setattr__(self, "_legacy_mode", legacy_mode)
        object.__setattr__(self, "_v21_mode", v21_mode)
        object.__setattr__(self, "_legacy_values", legacy_values)


@dataclass(frozen=True)
class GateSignals:
    included: bool = False
    incompatible: bool = False
    duplicate_function: bool = False
    no_valid_relation: bool = False
    safety_blocked: bool = False
    category_or_scene_only: bool = False
    food_blocked: bool = False
    needs_verification: bool = False
    product_type_unknown: bool = False
    safety_unverified: bool = False
    compatibility_unverified: bool = False
    duplication_unverified: bool = False
    safety_facts_insufficient: bool = False
    compatibility_facts_insufficient: bool = False
    reverse_dependency: bool = False
    purchase_direction: PurchaseDirection | None = None
    product_type_status: ProductTypeStatus | None = None


WEIGHTS = {
    "function_necessity": 30,
    "usage_continuity": 25,
    "scene_fit": 20,
    "enhancement_maintenance": 15,
    "natural_copurchase": 10,
}
V21_WEIGHTS = {
    "function_necessity": 30,
    "usage_continuity": 25,
    "purchase_direction": 15,
    "natural_copurchase": 15,
    "enhancement_maintenance": 10,
    "scene_fit": 5,
}
LEGACY_WEIGHTS = {
    "relation_strength": 30,
    "lifecycle_connection": 20,
    "repeat_value": 15,
    "function_gain": 10,
    "mental_copurchase": 10,
    "user_scene": 5,
}
MARKET_POINTS = {"E0": 0, "E1": 2, "E2": 5, "E3": 8, "E4": 10}
EVIDENCE_CAPS = {"E0": 59, "E1": 69, "E2": 79, "E3": 89, "E4": 100}


@dataclass(frozen=True)
class StickinessDecision:
    breakdown: Mapping[str, float]
    raw_score: float
    stickiness_score: float
    evidence_level: EvidenceLevel
    execution_status: ExecutionStatus
    decision_action: DecisionAction
    score_cap: int
    final_score: float
    recommendation: str
    rejected: bool
    rejection_codes: tuple[str, ...]
    hold_reasons: tuple[str, ...] = ()


_RATING_FIELDS = (
    "function_necessity",
    "usage_continuity",
    "scene_fit",
    "enhancement_maintenance",
    "natural_copurchase",
)
_V21_RATING_FIELDS = tuple(V21_WEIGHTS)
_LEGACY_RATING_FIELDS = tuple(LEGACY_WEIGHTS)
_HARD_REJECTIONS = (
    ("included", "included_item"),
    ("incompatible", "incompatible"),
    ("duplicate_function", "duplicate_function"),
    ("no_valid_relation", "no_valid_relation"),
    ("safety_blocked", "safety_blocked"),
    ("food_blocked", "food_blocked"),
    ("reverse_dependency", "reverse_dependency"),
)
_EVIDENCE_RANK = {level: index for index, level in enumerate(EvidenceLevel)}


def compute_stickiness(
    ratings: ScoreRatings,
    evidence_level: EvidenceLevel,
    gates: GateSignals,
) -> StickinessDecision:
    """Apply the approved stickiness score, gate, and cap rules."""
    evidence = EvidenceLevel(evidence_level)
    if ratings._v21_mode:
        return _compute_v21_stickiness(ratings, evidence, gates)
    if ratings._legacy_mode:
        values = ratings._legacy_values or (
            ratings.function_necessity,
            ratings.usage_continuity,
            ratings.enhancement_maintenance,
            ratings.enhancement_maintenance,
            ratings.natural_copurchase,
            ratings.scene_fit,
        )
        legacy_values = dict(zip(_LEGACY_RATING_FIELDS, values, strict=False))
        breakdown = {
            field: round(_clamp_rating(legacy_values[field]) / 5 * LEGACY_WEIGHTS[field], 1)
            for field in _LEGACY_RATING_FIELDS
        }
        breakdown["market_evidence"] = float(MARKET_POINTS[evidence.value])
    else:
        breakdown = {
            field: round(_clamp_rating(getattr(ratings, field)) / 5 * WEIGHTS[field], 1)
            for field in _RATING_FIELDS
        }
    raw_score = round(sum(breakdown.values()), 1)
    rejection_codes = tuple(
        code for signal, code in _HARD_REJECTIONS if getattr(gates, signal)
    )

    if rejection_codes:
        return StickinessDecision(
            breakdown=MappingProxyType(breakdown),
            raw_score=raw_score,
            stickiness_score=0.0,
            evidence_level=evidence,
            execution_status=ExecutionStatus.REJECT,
            decision_action=DecisionAction.NOT_RECOMMENDED,
            score_cap=0,
            final_score=0.0,
            recommendation="not_recommended",
            rejected=True,
            rejection_codes=rejection_codes,
        )

    score_cap = EVIDENCE_CAPS[evidence.value]
    if gates.category_or_scene_only:
        score_cap = min(score_cap, 49)
    if gates.needs_verification:
        score_cap = min(score_cap, 69)
    final_score = round(min(raw_score, score_cap), 1)
    return StickinessDecision(
        breakdown=MappingProxyType(breakdown),
        raw_score=raw_score,
        stickiness_score=final_score,
        evidence_level=evidence,
        execution_status=ExecutionStatus.PASS,
        decision_action=_legacy_decision_action(final_score),
        score_cap=score_cap,
        final_score=final_score,
        recommendation=_recommendation_for(final_score),
        rejected=False,
        rejection_codes=(),
    )


def _compute_v21_stickiness(
    ratings: ScoreRatings,
    evidence: EvidenceLevel,
    gates: GateSignals,
) -> StickinessDecision:
    breakdown = {
        field: round(_clamp_rating(getattr(ratings, field)) / 5 * V21_WEIGHTS[field], 1)
        for field in _V21_RATING_FIELDS
    }
    stickiness_score = round(sum(breakdown.values()), 1)
    rejection_codes = _v21_rejection_codes(gates)
    execution_status = _v21_execution_status(gates, rejection_codes)
    decision_action = _v21_decision_action(
        stickiness_score, evidence, execution_status
    )
    rejected = execution_status is ExecutionStatus.REJECT
    final_score = 0.0 if rejected else stickiness_score

    return StickinessDecision(
        breakdown=MappingProxyType(breakdown),
        raw_score=stickiness_score,
        stickiness_score=stickiness_score,
        evidence_level=evidence,
        execution_status=execution_status,
        decision_action=decision_action,
        score_cap=100,
        final_score=final_score,
        recommendation=_recommendation_for_action(decision_action),
        rejected=rejected,
        rejection_codes=rejection_codes,
        hold_reasons=_v21_hold_reasons(gates, rejection_codes),
    )


def _v21_rejection_codes(gates: GateSignals) -> tuple[str, ...]:
    codes = [code for signal, code in _HARD_REJECTIONS if getattr(gates, signal)]
    purchase_direction = (
        PurchaseDirection(gates.purchase_direction)
        if gates.purchase_direction is not None
        else None
    )
    product_type_status = (
        ProductTypeStatus(gates.product_type_status)
        if gates.product_type_status is not None
        else None
    )
    if purchase_direction is PurchaseDirection.REVERSE_DEPENDENCY and "reverse_dependency" not in codes:
        codes.append("reverse_dependency")
    if purchase_direction is PurchaseDirection.NONE and "no_valid_relation" not in codes:
        codes.append("no_valid_relation")
    if product_type_status is ProductTypeStatus.FOOD and "food_blocked" not in codes:
        codes.append("food_blocked")
    return tuple(codes)


def _v21_execution_status(
    gates: GateSignals, rejection_codes: tuple[str, ...]
) -> ExecutionStatus:
    product_type_status = (
        ProductTypeStatus(gates.product_type_status)
        if gates.product_type_status is not None
        else None
    )
    if rejection_codes:
        return ExecutionStatus.REJECT
    if (
        gates.product_type_unknown
        or product_type_status is ProductTypeStatus.UNKNOWN
        or gates.safety_unverified
        or gates.compatibility_unverified
        or gates.duplication_unverified
        or gates.safety_facts_insufficient
        or gates.compatibility_facts_insufficient
        or gates.needs_verification
    ):
        return ExecutionStatus.HOLD
    return ExecutionStatus.PASS


def _v21_hold_reasons(
    gates: GateSignals, rejection_codes: tuple[str, ...]
) -> tuple[str, ...]:
    if rejection_codes:
        return ()
    reasons = []
    if gates.product_type_unknown:
        reasons.append("product_type_unknown")
    if gates.safety_unverified or gates.safety_facts_insufficient:
        reasons.append("safety_verification_required")
    if gates.compatibility_unverified or gates.compatibility_facts_insufficient:
        reasons.append("compatibility_unverified")
    if gates.duplication_unverified:
        reasons.append("duplication_verification_required")
    return tuple(reasons)


def _v21_decision_action(
    score: float, evidence: EvidenceLevel, status: ExecutionStatus
) -> DecisionAction:
    if status is ExecutionStatus.REJECT or score < 70:
        return DecisionAction.NOT_RECOMMENDED
    if score < 78:
        return DecisionAction.OBSERVE
    if status is ExecutionStatus.HOLD or evidence in {EvidenceLevel.E0, EvidenceLevel.E1}:
        return DecisionAction.NEEDS_EVIDENCE
    if score >= 85 and evidence is EvidenceLevel.E4:
        return DecisionAction.FOCUS_DEVELOPMENT
    if score >= 85 and evidence is EvidenceLevel.E3:
        return DecisionAction.PRIORITY_TEST
    return DecisionAction.SMALL_BATCH_TEST


def _recommendation_for_action(action: DecisionAction) -> str:
    if action is DecisionAction.FOCUS_DEVELOPMENT:
        return "focus"
    if action in {DecisionAction.PRIORITY_TEST, DecisionAction.SMALL_BATCH_TEST}:
        return "test_pool"
    if action is DecisionAction.OBSERVE:
        return "observe"
    return "not_recommended"


def _legacy_decision_action(score: float) -> DecisionAction:
    if score >= 90:
        return DecisionAction.FOCUS_DEVELOPMENT
    if score >= 80:
        return DecisionAction.SMALL_BATCH_TEST
    if score >= 70:
        return DecisionAction.OBSERVE
    return DecisionAction.NOT_RECOMMENDED


T = TypeVar("T")


def sort_stickiness_decisions(
    items: Sequence[T],
    *,
    decision_getter: Callable[[T], StickinessDecision],
    evidence_getter: Callable[[T], EvidenceLevel],
    name_getter: Callable[[T], str],
) -> list[T]:
    """Return candidates in deterministic recommendation order without mutation."""

    def sort_key(item: T) -> tuple[int, float, float, int, float, str]:
        decision = decision_getter(item)
        if decision.rejected:
            return (1, 0.0, 0.0, 0, 0.0, name_getter(item))
        evidence = EvidenceLevel(evidence_getter(item))
        return (
            0,
            -decision.final_score,
            -decision.breakdown.get(
                "function_necessity", decision.breakdown.get("relation_strength", 0)
            ),
            -_EVIDENCE_RANK[evidence],
            -decision.breakdown.get(
                "enhancement_maintenance", decision.breakdown.get("repeat_value", 0)
            ),
            name_getter(item),
        )

    return sorted(items, key=sort_key)


def _clamp_rating(value: int) -> float:
    return min(5, max(0, value))


def _rating_value(
    values: Mapping[str, int | None], primary: str, *legacy: str
) -> int:
    for key in (primary, *legacy):
        value = values.get(key)
        if value is not None:
            return int(value)
    return 0


def _recommendation_for(score: float) -> str:
    if score >= 90:
        return "focus"
    if score >= 80:
        return "test_pool"
    if score >= 70:
        return "observe"
    return "not_recommended"


__all__ = [
    "EVIDENCE_CAPS",
    "MARKET_POINTS",
    "V21_WEIGHTS",
    "WEIGHTS",
    "EvidenceLevel",
    "GateSignals",
    "ScoreRatings",
    "StickinessDecision",
    "compute_stickiness",
    "sort_stickiness_decisions",
]
