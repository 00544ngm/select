import pytest

from app.domain.ingestible_classifier import classify_product_type
from app.domain.pairing_policy import ProductTypeStatus


@pytest.mark.parametrize(
    "title",
    [
        "stainless steel water bottle",
        "glass food storage container",
        "vitamin pill organizer",
        "electric pepper grinder",
        "pet feeding bowl",
        "external use facial cleansing brush",
        "automotive fuel filter",
    ],
)
def test_non_ingestible_products_are_allowed(title):
    assert classify_product_type(title).status is ProductTypeStatus.NON_FOOD


@pytest.mark.parametrize(
    "title",
    [
        "bottled spring water",
        "protein drink",
        "vitamin C tablets",
        "prescription oral medicine",
        "dog food",
        "pet joint supplement chews",
    ],
)
def test_ingestible_products_are_blocked(title):
    assert classify_product_type(title).status is ProductTypeStatus.INGESTIBLE


def test_missing_or_conflicting_product_type_is_unknown():
    assert classify_product_type("ACME Model X").status is ProductTypeStatus.UNKNOWN
    assert (
        classify_product_type("vitamin organizer with vitamin tablets").status
        is ProductTypeStatus.UNKNOWN
    )


@pytest.mark.parametrize(
    "title",
    [
        "Washable Sofa Cover",
        "Wireless Mouse",
        "Ceramic Brake Pad",
        "Cotton Shirt",
        "Titanium Drill Bit",
        "Reflective Dog Harness",
    ],
)
def test_cross_category_non_food_products_are_supported(title):
    assert classify_product_type(title).status is ProductTypeStatus.NON_FOOD


@pytest.mark.parametrize(
    "title",
    [
        "Chocolate Bar",
        "Cola Beverage",
        "Children Cough Syrup",
        "Multivitamin Gummies",
        "Premium Dog Kibble",
    ],
)
def test_cross_category_ingestible_products_are_blocked(title):
    assert classify_product_type(title).status is ProductTypeStatus.INGESTIBLE


@pytest.mark.parametrize(
    "title",
    [
        "LELE LIFE Metal Spatula Cooking Cast Iron 2pcs Griddle Spatula Turner",
        "Solid Wood Bedside Table with Drawer",
        "Cotton Crew Neck T Shirt",
        "Cordless Drill Driver Kit",
        "Stainless Steel Pet Feeding Bowl",
    ],
)
def test_high_confidence_non_food_entities_are_allowed(title):
    decision = classify_product_type(title)

    assert decision.status is ProductTypeStatus.NON_FOOD
    assert decision.reason == "confirmed non-ingestible entity evidence"


@pytest.mark.parametrize(
    "title",
    [
        "Chocolate Protein Bar 12 Count",
        "Vitamin C Gummies Dietary Supplement",
        "Chicken Flavor Dog Treats",
    ],
)
def test_food_examples_remain_ingestible(title):
    assert classify_product_type(title).status is ProductTypeStatus.INGESTIBLE


def test_strong_food_and_non_food_entity_evidence_conflict_is_unknown():
    decision = classify_product_type("Chocolate Protein Bar with Water Bottle")

    assert decision.status is ProductTypeStatus.UNKNOWN
    assert "water bottle" in decision.matched_terms
    assert "protein bar" in decision.matched_terms


def test_turner_name_does_not_override_milk_evidence():
    assert (
        classify_product_type("Turner Dairy Whole Milk").status
        is ProductTypeStatus.INGESTIBLE
    )


def test_description_non_food_context_does_not_override_olive_oil():
    decision = classify_product_type(
        "Organic olive oil",
        description="A pantry staple for the dining table",
    )

    assert decision.status is ProductTypeStatus.INGESTIBLE


def test_bare_turner_in_unrelated_title_is_unknown():
    assert (
        classify_product_type("Page Turner Book Club Novel").status
        is ProductTypeStatus.UNKNOWN
    )


@pytest.mark.parametrize(
    "title",
    [
        "Electric Milk Frother Handheld Foam Maker",
        "Milk Storage Bags for Breastfeeding",
    ],
)
def test_milk_accessories_are_non_food_entities(title):
    assert classify_product_type(title).status is ProductTypeStatus.NON_FOOD


def test_olive_oil_dispenser_conflict_is_not_ingestible():
    assert (
        classify_product_type("Olive Oil Dispenser Bottle for Kitchen").status
        is ProductTypeStatus.UNKNOWN
    )


def test_non_food_product_is_not_blocked_by_incidental_food_usage_in_bullets():
    decision = classify_product_type(
        "Doulami Ironing Board Tabletop Ironing Board with Iron Rest",
        keywords=[
            "It doubles as a kids' drawing table, a compact desk, or a casual snack table."
        ],
    )

    assert decision.status is ProductTypeStatus.NON_FOOD
