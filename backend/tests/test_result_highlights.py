from backend.application.result_highlights import extract_result_highlights


def test_extracts_actual_highest_scoring_direction():
    payload = {
        "product_title": "Pizza Cutter",
        "product_images": ["https://images.example/main.jpg"],
        "structured_directions": [
            {"name": "方向甲", "score": 70, "type": "便利型", "keywords": {}},
            {
                "name": "防滑披萨切割垫",
                "score": 91,
                "type": "低成本附加",
                "keywords": {"en": "non slip pizza cutting mat"},
            },
        ],
    }

    result = extract_result_highlights(payload)

    assert result == {
        "provider": None,
        "provider_model": None,
        "product_title": "Pizza Cutter",
        "product_title_zh": None,
        "product_id": None,
        "product_image": "https://images.example/main.jpg",
        "top_direction_name": "防滑披萨切割垫",
        "top_direction_keywords": {"en": "non slip pizza cutting mat"},
        "top_direction_score": 91.0,
        "top_direction_type": "低成本附加",
    }


def test_uses_primary_model_when_only_nested_payload_has_highlights():
    payload = {
        "models": {
            "gpt": {
                "product_title": "Primary",
                "structured_directions": [
                    {"name": "Primary Direction", "score": 88}
                ],
            },
            "deepseek": {
                "product_title": "Secondary",
                "structured_directions": [
                    {"name": "Secondary Direction", "score": 99}
                ],
            },
        }
    }

    result = extract_result_highlights(payload)

    assert result["product_title"] == "Primary"
    assert result["top_direction_name"] == "Primary Direction"


def test_returns_empty_highlights_for_old_or_missing_payload():
    assert extract_result_highlights(None) == {}
    assert extract_result_highlights({"grade": "A"}) == {
        "provider": None,
        "provider_model": None,
        "product_title": None,
        "product_title_zh": None,
        "product_id": None,
        "product_image": None,
        "top_direction_name": None,
        "top_direction_keywords": {},
        "top_direction_score": None,
        "top_direction_type": None,
    }


def test_prefers_v2_final_score_and_ignores_rejected_direction():
    payload = {
        "product_title": "Printer",
        "structured_directions": [
            {"name": "Rejected", "score": 99, "final_score": 0, "rejected": True},
            {"name": "Accepted", "score": 80, "final_score": 82, "rejected": False},
        ],
    }

    result = extract_result_highlights(payload)

    assert result["top_direction_name"] == "Accepted"
    assert result["top_direction_score"] == 82.0


def test_falls_back_to_legacy_score_when_final_score_is_zero():
    payload = {
        "structured_directions": [
            {"name": "Legacy", "score": 76, "final_score": 0},
        ],
    }

    result = extract_result_highlights(payload)

    assert result["top_direction_name"] == "Legacy"
    assert result["top_direction_score"] == 76.0


def test_extracts_persisted_provider_identity_for_history_without_guessing():
    payload = {
        "models": {
            "gpt": {
                "provider": "custom",
                "provider_model": "claude-test",
                "product_title": "Printer",
                "structured_directions": [],
            },
            "deepseek": {"provider": "deepseek", "provider_model": "deepseek-chat"},
        },
        "provider": "request-provider-should-not-be-used",
        "provider_model": "request-model-should-not-be-used",
    }

    result = extract_result_highlights(payload)

    assert result["provider"] == "custom"
    assert result["provider_model"] == "claude-test"


def test_history_identity_is_missing_when_old_payload_has_no_persisted_identity():
    result = extract_result_highlights({"models": {"gpt": {"product_title": "Old"}}})

    assert result["provider"] is None
    assert result["provider_model"] is None


def test_history_uses_first_persisted_model_when_dual_payload_has_no_legacy_gpt_key():
    result = extract_result_highlights({
        "models": {
            "reviewer_a": {
                "provider": "custom",
                "provider_model": "model-a",
                "product_title": "Custom primary",
                "structured_directions": [],
            },
            "reviewer_b": {"provider": "other", "provider_model": "model-b"},
        }
    })

    assert result["product_title"] == "Custom primary"
    assert result["provider"] == "custom"
