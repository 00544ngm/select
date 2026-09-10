from app.domain.product_pairing_filter import classify_candidate
from app.domain.schemas import HypothesisOutput


def test_food_is_rejected_but_non_food_consumable_is_kept():
    assert classify_candidate("Whole Black Peppercorns").status == "food"
    assert classify_candidate("Replacement Ink Cartridge").status == "allowed"


def test_explicit_sea_salt_food_is_not_overridden_by_grinder_keywords():
    result = classify_candidate(
        "Coarse Sea Salt",
        keywords={"en": "coarse sea salt grinder refill"},
    )

    assert result.status == "food"
    assert "coarse sea salt" in result.matched_terms


def test_explicit_culinary_seeds_are_food():
    assert classify_candidate("Whole Cumin Seeds").status == "food"
    assert classify_candidate("Whole Coriander Seeds").status == "food"


def test_unknown_food_classification_is_not_recommended():
    result = classify_candidate("Natural refill product")

    assert result.status == "needs_verification"


def test_classifier_uses_type_and_description_when_title_is_ambiguous():
    result = classify_candidate(
        "Refill product",
        product_type="food seasoning",
        description="A pantry ingredient for cooking",
    )

    assert result.status == "food"
    assert "seasoning" in result.matched_terms


def test_classifier_keeps_non_food_filter_even_when_refill_is_ambiguous():
    result = classify_candidate(
        "Replacement filter refill",
        product_type="water filter cartridge",
    )

    assert result.status == "allowed"
    assert "filter" in result.matched_terms


def test_non_food_context_does_not_trigger_generic_food_words():
    assert classify_candidate("Spice Rack").status == "allowed"
    assert classify_candidate("Spice Storage Jars Glass").status == "allowed"
    assert classify_candidate("Portable Spice Organizer Case").status == "allowed"
    assert classify_candidate("Electric Spice Grinder").status == "allowed"
    assert classify_candidate("Food Processor").status == "allowed"
    assert classify_candidate("Food Processor Replacement Blade").status == "allowed"


def test_cross_category_non_food_products_are_allowed():
    assert classify_candidate("Camera Lens").status == "allowed"
    assert classify_candidate("USB-C Charging Cable").status == "allowed"
    assert classify_candidate("Kitchen Scissors").status == "allowed"


def test_hypothesis_contract_defaults_new_link_and_filter_fields():
    output = HypothesisOutput.model_validate(
        {
            "model_version": "combination_model_v2.0",
            "product_profile": {
                "title_zh": "产品",
                "core_purchase_job": "完成任务",
            },
        }
    )

    assert output.product_profile.source_url == ""
    assert output.product_profile.product_type == ""
    assert output.directions == []
