from app.domain.dto import ProductDTO
from app.domain.product_facts import (
    build_product_facts,
    render_product_facts,
    validate_fact_ids,
)


def test_builds_stable_facts_for_every_collected_source_field():
    product = ProductDTO(
        url="https://www.walmart.com/ip/camera/123",
        title="Camera",
        price="$99",
        rating="4.5",
        review_count="20",
        bullet_points=["Includes battery", "USB-C charging"],
        description="Compact camera",
        attributes={"Color": "Black"},
        review_snippets=["Battery lasts all day"],
        qa_pairs=[{"q": "Battery included?", "a": "Yes"}],
        fbt_items=[{"title": "Memory Card"}],
    )

    facts = build_product_facts(product)

    assert [fact.fact_id for fact in facts] == [
        "url",
        "title",
        "price",
        "rating",
        "review_count",
        "bullet:0",
        "bullet:1",
        "description",
        "attribute:Color",
        "review:0",
        "qa:0",
        "fbt:0",
    ]
    assert facts[-2].text == '{"a": "Yes", "q": "Battery included?"}'
    assert facts[-1].text == '{"title": "Memory Card"}'


def test_omits_empty_values_and_renders_only_server_facts():
    facts = build_product_facts(ProductDTO(title="Camera", bullet_points=["", "Includes battery"]))

    assert [fact.fact_id for fact in facts] == ["title", "bullet:1"]
    assert render_product_facts(facts) == (
        "[title] Title: Camera\n[bullet:1] Bullet point: Includes battery"
    )


def test_unknown_and_duplicate_source_references_are_reported():
    facts = build_product_facts(ProductDTO(title="Camera", bullet_points=["Includes battery"]))

    valid, invalid = validate_fact_ids(
        ["title", "bullet:0", "title", "bullet:99", "", "bullet:99"], facts
    )

    assert valid == ("title", "bullet:0")
    assert invalid == ("bullet:99",)
