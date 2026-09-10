from __future__ import annotations

import pytest

from backend.application.result_quality import (
    RESULT_WITH_CANDIDATES,
    ResultQualityError,
    validate_hypothesis_payload,
)

QUALIFIED_MESSAGE = (
    "分析已完成，发现达到高粘性门槛的候选，请按候选最终动作执行。"
)
NEEDS_EVIDENCE_MESSAGE = (
    "发现潜在方向，但当前不可执行，请先补齐兼容、安全或商品类型证据。"
)
NO_CANDIDATES_MESSAGE = (
    "分析已完成，未发现达到高粘性门槛的辅品，不建议为了凑数量强行组合。"
)


def _direction(**overrides):
    direction = {
        "name": "Compatible Filter",
        "model_version": "combination_model_v2.1",
        "primary_relation": "consumable_refill",
        "purchase_direction": "forward_dependency",
        "product_type_status": "non_food",
        "food_filter_status": "allowed",
        "compatibility_status": "clear",
        "duplication_status": "clear",
        "safety_status": "clear",
        "source_fact_ids": ["title"],
        "incompatibility_reason": "",
        "duplicate_function_reason": "",
        "safety_risk": "",
        "score_breakdown": {
            "function_necessity": 30,
            "usage_continuity": 25,
            "purchase_direction": 15,
            "scene_fit": 15,
            "enhancement_maintenance": 10,
            "natural_copurchase": 5,
        },
        "evidence_level": "E2",
        "execution_status": "pass",
        "decision_action": "small_batch_test",
        "rejection_codes": [],
    }
    direction.update(overrides)
    return direction


def _payload(directions=None, **overrides):
    directions = [_direction()] if directions is None else directions
    payload = {
        "mode": "hypothesis",
        "model_version": "combination_model_v2.1",
        "directions_count": len(directions),
        "structured_directions": directions,
        "result_status": "completed_with_qualified_candidates",
        "result_message": QUALIFIED_MESSAGE,
        "raw_direction_count": len(directions),
        "qualified_direction_count": 1 if directions else 0,
        "hold_direction_count": 0,
        "rejected_direction_count": 0,
        "rejection_summary": {},
        "audit_performed": False,
        "audit_reason": "",
        "initial_raw_direction_count": len(directions),
        "audit_raw_direction_count": 0,
        "audit_outcome": "",
    }
    if not directions:
        payload.update(
            result_status="completed_no_qualified_candidates",
            audit_performed=True,
            audit_reason="initial_v2.1_directions_empty",
            audit_outcome="confirmed_no_candidates",
        )
    payload.update(overrides)
    return payload


def test_valid_v21_hypothesis_payload_passes_quality_gate():
    validate_hypothesis_payload(
        _payload(), expected_model_version="combination_model_v2.1"
    )


@pytest.mark.parametrize(
    "payload",
    [
        _payload(model_version="combination_model_v2.0"),
        _payload(directions_count=2),
        _payload(raw_direction_count=2),
        _payload(qualified_direction_count=0),
        _payload(directions=[_direction(model_version="combination_model_v2.0")]),
        _payload(directions=[_direction(purchase_direction="reverse_dependency")]),
        _payload(directions=[_direction(primary_relation="weak_context")]),
        _payload(directions=[_direction(product_type_status="food")]),
        _payload(directions=[_direction(food_filter_status="food")]),
        _payload(directions=[_direction(rejection_codes=["included_item"])]),
        _payload(directions=[_direction(score_breakdown={})]),
        _payload(directions=[], audit_performed=False),
        _payload(directions=[], result_message=""),
    ],
)
def test_invalid_v21_payload_fails_quality_gate(payload):
    with pytest.raises(ResultQualityError) as error:
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )

    assert error.value.code == "RESULT_QUALITY_INVALID"
    assert error.value.retryable is False


def test_legacy_payload_without_contract_is_not_reinterpreted():
    validate_hypothesis_payload(
        {"model_version": "combination_model_v2.0", "directions_count": 0},
        expected_model_version=None,
    )


def _review(status="confirmed_non_food", **overrides):
    review = {
        "status": status,
        "source": "model",
        "confidence": 0.95,
        "reason": "商品事实支持该类型结论",
        "evidence": [
            {
                "source_field": "name_en",
                "verbatim_quote": "Compatible Filter",
            }
        ],
        "action": "continue",
    }
    review.update(overrides)
    return review


@pytest.mark.parametrize(
    ("direction", "message"),
    [
        (
            _direction(product_type_review=_review("confirmed_food", action="block")),
            "confirmed_food candidate must be rejected",
        ),
        (
            _direction(
                product_type_review=_review("confirmed_food", action="block"),
                execution_status="reject",
                decision_action="not_recommended",
                rejection_codes=["no_valid_relation"],
            ),
            "food rejection code",
        ),
        (
            _direction(
                product_type_review=_review(
                    "confirmed_food", action="block", evidence=[]
                ),
                execution_status="reject",
                decision_action="not_recommended",
                rejection_codes=["food_product"],
            ),
            "located evidence",
        ),
    ],
)
def test_confirmed_food_review_requires_reject_food_code_and_located_evidence(
    direction, message
):
    with pytest.raises(ResultQualityError, match=message):
        validate_hypothesis_payload(
            _payload(directions=[direction]),
            expected_model_version="combination_model_v2.1",
        )


def test_valid_confirmed_food_rejection_passes_quality_gate():
    direction = _direction(
        product_type_review=_review("confirmed_food", action="block"),
        product_type_status="food",
        food_filter_status="food",
        execution_status="reject",
        decision_action="not_recommended",
        rejection_codes=["food_product"],
    )
    validate_hypothesis_payload(
        _payload(
            directions=[direction],
            result_status="completed_no_qualified_candidates",
            result_message=NO_CANDIDATES_MESSAGE,
            qualified_direction_count=0,
            rejected_direction_count=1,
            rejection_summary={"food_product": 1},
        ),
        expected_model_version="combination_model_v2.1",
    )


def test_fabricated_food_quote_cannot_trigger_hard_rejection():
    direction = _direction(
        product_type_review=_review(
            "confirmed_food",
            action="block",
            evidence=[
                {
                    "source_field": "name_en",
                    "verbatim_quote": "Invented edible product",
                }
            ],
        ),
        product_type_status="food",
        food_filter_status="food",
        execution_status="reject",
        decision_action="not_recommended",
        rejection_codes=["food_product"],
    )

    with pytest.raises(ResultQualityError, match="anchored evidence"):
        validate_hypothesis_payload(
            _payload(directions=[direction]),
            expected_model_version="combination_model_v2.1",
        )


@pytest.mark.parametrize("status", ["likely_non_food", "needs_review"])
def test_uncertain_product_review_requires_evidence_without_changing_score(status):
    direction = _direction(
        score=87,
        final_score=87,
        product_type_review=_review(
            status,
            confidence=0.55,
            action="continue_with_review",
        ),
    )
    validate_hypothesis_payload(
        _payload(
            directions=[direction],
            result_status="completed_needs_evidence",
            result_message=NEEDS_EVIDENCE_MESSAGE,
            qualified_direction_count=0,
            hold_direction_count=1,
        ),
        expected_model_version="combination_model_v2.1",
    )
    assert direction["final_score"] == 87


def test_confirmed_non_food_review_passes_normally():
    validate_hypothesis_payload(
        _payload(directions=[_direction(product_type_review=_review())]),
        expected_model_version="combination_model_v2.1",
    )


def test_blocked_gate_requires_reason_and_source_fact():
    direction = _direction(
        compatibility_status="blocked",
        incompatibility_reason="",
        source_fact_ids=[],
        execution_status="reject",
        rejection_codes=["incompatible"],
    )
    with pytest.raises(ResultQualityError, match="blocked gate lacks evidence"):
        validate_hypothesis_payload(
            _payload(
                directions=[direction],
                result_status="completed_no_qualified_candidates",
                result_message=NO_CANDIDATES_MESSAGE,
                qualified_direction_count=0,
                rejected_direction_count=1,
                rejection_summary={"incompatible": 1},
            ),
            expected_model_version="combination_model_v2.1",
        )


def test_reject_candidate_requires_at_least_one_rejection_code():
    direction = _direction(
        execution_status="reject",
        decision_action="not_recommended",
        rejection_codes=[],
    )

    with pytest.raises(
        ResultQualityError,
        match="Reject candidate must carry at least one rejection code",
    ):
        validate_hypothesis_payload(
            _payload(
                directions=[direction],
                result_status="completed_no_qualified_candidates",
                result_message=NO_CANDIDATES_MESSAGE,
                qualified_direction_count=0,
                rejected_direction_count=1,
            ),
            expected_model_version="combination_model_v2.1",
        )


def test_non_reject_candidate_cannot_carry_rejection_codes():
    direction = _direction(
        execution_status="hold",
        decision_action="needs_evidence",
        rejection_codes=["incompatible"],
    )

    with pytest.raises(
        ResultQualityError,
        match="Non-reject candidate cannot carry rejection codes",
    ):
        validate_hypothesis_payload(
            _payload(
                directions=[direction],
                result_status="completed_needs_evidence",
                result_message=NEEDS_EVIDENCE_MESSAGE,
                qualified_direction_count=0,
                hold_direction_count=1,
            ),
            expected_model_version="combination_model_v2.1",
        )


def test_repeated_multi_rejection_pattern_is_invalid():
    directions = [
        _direction(
            name=f"candidate-{index}",
            compatibility_status="blocked",
            duplication_status="blocked",
            safety_status="blocked",
            incompatibility_reason="confirmed",
            duplicate_function_reason="confirmed",
            safety_risk="confirmed",
            execution_status="reject",
            rejection_codes=[
                "incompatible",
                "duplicate_function",
                "safety_blocked",
            ],
        )
        for index in range(8)
    ]
    with pytest.raises(ResultQualityError, match="suspicious rejection pattern"):
        validate_hypothesis_payload(
            _payload(
                directions=directions,
                result_status="completed_no_qualified_candidates",
                result_message=NO_CANDIDATES_MESSAGE,
                qualified_direction_count=0,
                rejected_direction_count=8,
                rejection_summary={
                    "duplicate_function": 8,
                    "incompatible": 8,
                    "safety_blocked": 8,
                },
            ),
            expected_model_version="combination_model_v2.1",
        )


def test_dual_payload_reports_model_and_missing_score_dimensions():
    payload = {
        "models": {
            "gpt": _payload(),
            "deepseek": _payload(directions=[_direction(score_breakdown={})]),
        },
        **_payload(),
    }

    with pytest.raises(ResultQualityError, match="deepseek.*function_necessity"):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


def test_summary_rejects_unknown_execution_status_in_payload():
    payload = _payload(
        directions=[_direction(execution_status="unknown")],
        result_status="completed_no_qualified_candidates",
        qualified_direction_count=0,
        rejected_direction_count=0,
    )

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


def test_rejection_summary_must_match_direction_rejection_codes():
    payload = _payload(
        directions=[
            _direction(
                execution_status="reject",
                decision_action="not_recommended",
                rejection_codes=["weak_context"],
            )
        ],
        result_status="completed_no_qualified_candidates",
        qualified_direction_count=0,
        rejected_direction_count=1,
        rejection_summary={},
    )

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


@pytest.mark.parametrize(
    "illegal_code",
    ["reverse_dependency", "none", "weak_context", "food", "included_item"],
)
def test_pass_candidate_cannot_carry_illegal_rejection_code(illegal_code):
    payload = _payload(directions=[_direction(rejection_codes=[illegal_code])])

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


def test_zero_direction_requires_complete_audit_fields():
    payload = _payload(directions=[], audit_reason="", result_message="confirmed")

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


def test_dual_model_payload_validates_every_model():
    primary = _payload()
    secondary = _payload(model_version="combination_model_v2.0")
    payload = {**primary, "models": {"gpt": primary, "deepseek": secondary}}

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


def test_zero_direction_audit_can_recover_candidates():
    direction = _direction()
    payload = _payload(
        directions=[direction],
        audit_performed=True,
        audit_reason="initial_v2.1_directions_empty",
        initial_raw_direction_count=0,
        audit_raw_direction_count=1,
        audit_outcome="recovered_candidates",
    )
    validate_hypothesis_payload(
        payload, expected_model_version="combination_model_v2.1"
    )


@pytest.mark.parametrize(
    "directions",
    [
        [None],
        [_direction(rejection_codes=None)],
        [_direction(rejection_codes="food_blocked")],
        [_direction(execution_status=["pass"])],
        [_direction(primary_relation=["consumable_refill"])],
        [_direction(purchase_direction=["forward_dependency"])],
        [_direction(evidence_level=["E2"])],
        [_direction(decision_action=["small_batch_test"])],
        [
            _direction(
                score_breakdown={
                    key: str(value)
                    for key, value in _direction()["score_breakdown"].items()
                }
            )
        ],
    ],
)
def test_malformed_direction_shapes_raise_stable_quality_error(directions):
    with pytest.raises(ResultQualityError) as error:
        validate_hypothesis_payload(
            _payload(directions=directions),
            expected_model_version="combination_model_v2.1",
        )

    assert error.value.code == "RESULT_QUALITY_INVALID"


@pytest.mark.parametrize(
    "models",
    [
        None,
        [],
        {},
        {"gpt": _payload()},
        {"gpt": _payload(), "deepseek": _payload(), "other": _payload()},
        {"gpt": _payload(), "deepseek": None},
    ],
)
def test_models_wrapper_requires_exactly_two_valid_model_payloads(models):
    payload = {**_payload(), "models": models}

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


def test_valid_dual_model_payload_passes_quality_gate():
    primary = _payload()
    secondary = _payload()

    validate_hypothesis_payload(
        {**primary, "models": {"gpt": primary, "deepseek": secondary}},
        expected_model_version="combination_model_v2.1",
    )


def test_dual_model_payload_also_validates_top_level_primary():
    valid = _payload()
    payload = {
        **valid,
        "result_message": "损坏的顶层文案",
        "models": {"gpt": valid, "deepseek": valid},
    }

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


@pytest.mark.parametrize(
    "direction",
    [
        _direction(product_type_status="unknown"),
        _direction(food_filter_status="needs_verification"),
        _direction(rejection_codes=["food_blocked"]),
        _direction(rejection_codes=["safety_blocked"]),
    ],
)
def test_pass_requires_verified_non_food_without_rejection_codes(direction):
    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            _payload(directions=[direction]),
            expected_model_version="combination_model_v2.1",
        )


def test_result_message_must_match_computed_status():
    payload = _payload(
        result_status=RESULT_WITH_CANDIDATES,
        result_message="未发现合格候选",
    )

    with pytest.raises(ResultQualityError):
        validate_hypothesis_payload(
            payload, expected_model_version="combination_model_v2.1"
        )


@pytest.mark.parametrize(
    "payload",
    [
        _payload(),
        _payload(
            directions=[
                _direction(
                    execution_status="hold",
                    decision_action="collect_evidence",
                )
            ],
            result_status="completed_needs_evidence",
            result_message=NEEDS_EVIDENCE_MESSAGE,
            qualified_direction_count=0,
            hold_direction_count=1,
        ),
        _payload(
            directions=[
                _direction(
                    execution_status="reject",
                    decision_action="not_recommended",
                    rejection_codes=["no_valid_relation"],
                )
            ],
            result_status="completed_no_qualified_candidates",
            result_message=NO_CANDIDATES_MESSAGE,
            qualified_direction_count=0,
            rejected_direction_count=1,
            rejection_summary={"no_valid_relation": 1},
        ),
    ],
)
def test_each_result_status_accepts_only_its_canonical_message(payload):
    validate_hypothesis_payload(
        payload, expected_model_version="combination_model_v2.1"
    )
