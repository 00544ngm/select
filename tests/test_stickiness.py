from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.stickiness import (
    EvidenceLevel,
    GateSignals,
    ScoreRatings,
    compute_stickiness,
    sort_stickiness_decisions,
)

V21_RATINGS = ScoreRatings(
    function_necessity=5,
    usage_continuity=5,
    purchase_direction=5,
    natural_copurchase=5,
    enhancement_maintenance=5,
    scene_fit=5,
)


def test_v21_uses_six_relationship_dimensions_without_an_evidence_cap():
    result = compute_stickiness(V21_RATINGS, EvidenceLevel.E0, GateSignals())

    assert dict(result.breakdown) == {
        "function_necessity": 30.0,
        "usage_continuity": 25.0,
        "purchase_direction": 15.0,
        "natural_copurchase": 15.0,
        "enhancement_maintenance": 10.0,
        "scene_fit": 5.0,
    }
    assert result.stickiness_score == 100.0
    assert result.final_score == 100.0
    assert result.evidence_level == EvidenceLevel.E0


def test_unknown_product_type_is_hold_not_a_69_score_cap():
    result = compute_stickiness(
        V21_RATINGS,
        EvidenceLevel.E4,
        GateSignals(product_type_unknown=True),
    )

    assert result.stickiness_score == 100.0
    assert result.final_score == 100.0
    assert result.execution_status == "hold"
    assert result.rejected is False


def test_reverse_dependency_is_rejected_without_overwriting_stickiness():
    result = compute_stickiness(
        V21_RATINGS,
        EvidenceLevel.E4,
        GateSignals(reverse_dependency=True),
    )

    assert result.stickiness_score == 100.0
    assert result.rejection_codes == ("reverse_dependency",)
    assert result.execution_status == "reject"


@pytest.mark.parametrize(
    ("ratings", "evidence", "expected_breakdown", "raw_score"),
    [
        (
            ScoreRatings(5, 5, 5, 5, 5, 5),
            EvidenceLevel.E4,
            {
                "relation_strength": 30.0,
                "lifecycle_connection": 20.0,
                "repeat_value": 15.0,
                "function_gain": 10.0,
                "mental_copurchase": 10.0,
                "market_evidence": 10.0,
                "user_scene": 5.0,
            },
            100.0,
        ),
        (
            ScoreRatings(1, 2, 3, 4, 5, 0),
            EvidenceLevel.E2,
            {
                "relation_strength": 6.0,
                "lifecycle_connection": 8.0,
                "repeat_value": 9.0,
                "function_gain": 8.0,
                "mental_copurchase": 10.0,
                "market_evidence": 5.0,
                "user_scene": 0.0,
            },
            46.0,
        ),
    ],
)
def test_calculates_exact_weighted_components_and_total(
    ratings: ScoreRatings,
    evidence: EvidenceLevel,
    expected_breakdown: dict[str, float],
    raw_score: float,
):
    result = compute_stickiness(ratings, evidence, GateSignals())

    assert dict(result.breakdown) == expected_breakdown
    assert result.raw_score == raw_score
    assert result.final_score == raw_score


@pytest.mark.parametrize(
    ("evidence", "expected_cap", "expected_raw_score"),
    [
        (EvidenceLevel.E0, 59, 90.0),
        (EvidenceLevel.E1, 69, 92.0),
        (EvidenceLevel.E2, 79, 95.0),
        (EvidenceLevel.E3, 89, 98.0),
        (EvidenceLevel.E4, 100, 100.0),
    ],
)
def test_evidence_levels_apply_their_caps(
    evidence: EvidenceLevel, expected_cap: int, expected_raw_score: float
):
    result = compute_stickiness(
        ScoreRatings(5, 5, 5, 5, 5, 5), evidence, GateSignals()
    )

    assert result.raw_score == expected_raw_score
    assert result.score_cap == expected_cap
    assert result.final_score == expected_cap


def test_category_or_scene_only_cap_overrides_evidence_cap():
    result = compute_stickiness(
        ScoreRatings(5, 5, 5, 5, 5, 5),
        EvidenceLevel.E4,
        GateSignals(category_or_scene_only=True),
    )

    assert result.score_cap == 49
    assert result.final_score == 49
    assert result.rejected is False


@pytest.mark.parametrize(
    ("ratings", "final_score", "recommendation"),
    [
        (ScoreRatings(5, 5, 0, 2, 2, 1), 69, "not_recommended"),
        (ScoreRatings(5, 5, 0, 0, 5, 0), 70, "observe"),
        (ScoreRatings(5, 5, 5, 0, 2, 0), 79, "observe"),
        (ScoreRatings(5, 5, 5, 0, 0, 5), 80, "test_pool"),
        (ScoreRatings(5, 5, 5, 5, 2, 0), 89, "test_pool"),
        (ScoreRatings(5, 5, 5, 5, 0, 5), 90, "focus"),
    ],
)
def test_recommendation_boundaries(
    ratings: ScoreRatings, final_score: int, recommendation: str
):
    result = compute_stickiness(
        ratings, EvidenceLevel.E4, GateSignals()
    )

    assert result.final_score == final_score
    assert result.recommendation == recommendation


@pytest.mark.parametrize(
    ("gates", "expected_codes"),
    [
        (GateSignals(included=True), ("included_item",)),
        (GateSignals(incompatible=True), ("incompatible",)),
        (GateSignals(duplicate_function=True), ("duplicate_function",)),
        (GateSignals(safety_blocked=True), ("safety_blocked",)),
        (GateSignals(no_valid_relation=True), ("no_valid_relation",)),
        (
            GateSignals(included=True, incompatible=True, safety_blocked=True),
            ("included_item", "incompatible", "safety_blocked"),
        ),
    ],
)
def test_hard_gates_reject_before_caps(
    gates: GateSignals, expected_codes: tuple[str, ...]
):
    result = compute_stickiness(
        ScoreRatings(5, 5, 5, 5, 5, 5), EvidenceLevel.E4, gates
    )

    assert result.rejected is True
    assert result.final_score == 0
    assert result.rejection_codes == expected_codes


def test_ratings_are_clamped_and_decision_is_deeply_immutable():
    result = compute_stickiness(
        ScoreRatings(-4, 10, 6, -1, 5, 9), EvidenceLevel.E0, GateSignals()
    )

    assert dict(result.breakdown) == {
        "relation_strength": 0.0,
        "lifecycle_connection": 20.0,
        "repeat_value": 15.0,
        "function_gain": 0.0,
        "mental_copurchase": 10.0,
        "market_evidence": 0.0,
        "user_scene": 5.0,
    }
    with pytest.raises(TypeError):
        result.breakdown["relation_strength"] = 99.0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.final_score = 99  # type: ignore[misc]


def test_sorting_is_deterministic_and_does_not_mutate_input():
    decisions = [
        ("zeta", compute_stickiness(ScoreRatings(5, 5, 4, 4, 0, 0), EvidenceLevel.E4, GateSignals())),
        ("beta", compute_stickiness(ScoreRatings(5, 5, 5, 0, 1, 5), EvidenceLevel.E3, GateSignals())),
        ("aardvark", compute_stickiness(ScoreRatings(5, 5, 5, 0, 1, 5), EvidenceLevel.E3, GateSignals())),
        ("alpha", compute_stickiness(ScoreRatings(5, 5, 5, 0, 0, 5), EvidenceLevel.E4, GateSignals())),
        ("gamma", compute_stickiness(ScoreRatings(5, 5, 5, 5, 5, 5), EvidenceLevel.E4, GateSignals(included=True))),
    ]

    ordered = sort_stickiness_decisions(
        decisions,
        decision_getter=lambda item: item[1],
        evidence_getter=lambda item: (
            EvidenceLevel.E3
            if item[0] in {"beta", "aardvark"}
            else EvidenceLevel.E4
        ),
        name_getter=lambda item: item[0],
    )

    assert [name for name, _ in decisions] == ["zeta", "beta", "aardvark", "alpha", "gamma"]
    assert [name for name, _ in ordered] == ["alpha", "zeta", "aardvark", "beta", "gamma"]


def test_sorting_prefers_relation_strength_before_evidence_level():
    stronger_relation = compute_stickiness(
        ScoreRatings(5, 5, 5, 3, 0, 0), EvidenceLevel.E3, GateSignals()
    )
    stronger_evidence = compute_stickiness(
        ScoreRatings(4, 5, 5, 0, 5, 0), EvidenceLevel.E4, GateSignals()
    )
    assert stronger_relation.final_score == stronger_evidence.final_score == 79

    ordered = sort_stickiness_decisions(
        [
            ("stronger evidence", stronger_evidence, EvidenceLevel.E4),
            ("stronger relation", stronger_relation, EvidenceLevel.E3),
        ],
        decision_getter=lambda item: item[1],
        evidence_getter=lambda item: item[2],
        name_getter=lambda item: item[0],
    )

    assert [name for name, _, _ in ordered] == [
        "stronger relation",
        "stronger evidence",
    ]


def test_link_driven_score_uses_five_dimensions_without_market_points():
    result = compute_stickiness(
        ScoreRatings(
            function_necessity=5,
            usage_continuity=5,
            scene_fit=5,
            enhancement_maintenance=4,
            natural_copurchase=5,
        ),
        EvidenceLevel.E4,
        GateSignals(),
    )

    assert dict(result.breakdown) == {
        "function_necessity": 30.0,
        "usage_continuity": 25.0,
        "scene_fit": 20.0,
        "enhancement_maintenance": 12.0,
        "natural_copurchase": 10.0,
    }
    assert result.raw_score == 97.0
    assert result.final_score == 97.0


def test_food_is_hard_rejected_and_unknown_is_capped_for_verification():
    food = compute_stickiness(
        ScoreRatings(function_necessity=5, usage_continuity=5, scene_fit=5,
                     enhancement_maintenance=5, natural_copurchase=5),
        EvidenceLevel.E4,
        GateSignals(food_blocked=True),
    )
    unknown = compute_stickiness(
        ScoreRatings(function_necessity=5, usage_continuity=5, scene_fit=5,
                     enhancement_maintenance=5, natural_copurchase=5),
        EvidenceLevel.E4,
        GateSignals(needs_verification=True),
    )

    assert food.rejected is True
    assert "food_blocked" in food.rejection_codes
    assert unknown.rejected is False
    assert unknown.score_cap == 69
    assert unknown.final_score == 69
