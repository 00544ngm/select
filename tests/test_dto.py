"""Tests for domain DTOs — creation, defaults, serialization, deserialization."""
from __future__ import annotations

from dataclasses import asdict

from app.domain.dto import (
    DirectionDTO,
    HypothesisDTO,
    HypothesisResultDTO,
    JudgmentResultDTO,
    ProductDTO,
)


def test_product_dto_defaults():
    dto = ProductDTO(url="https://walmart.com/foo")
    assert dto.url == "https://walmart.com/foo"
    assert dto.title == ""
    assert dto.price == ""
    assert dto.rating == ""
    assert dto.review_count == ""
    assert dto.bullet_points == []
    assert dto.attributes == {}
    assert dto.images == []
    assert dto.description is None
    assert dto.fbt_items == []
    assert dto.review_snippets == []
    assert dto.qa_pairs == []


def test_product_dto_full():
    dto = ProductDTO(
        url="https://walmart.com/bar",
        title="Test Product",
        price="$19.99",
        original_price="$29.99",
        rating="4.5",
        review_count="1234",
        bullet_points=["Feature A", "Feature B"],
        attributes={"Color": "Red", "Size": "M"},
        images=["img1.jpg"],
        description="A great product.",
        fbt_items=[{"title": "Batteries"}],
        review_snippets=["Great product!"],
        qa_pairs=[{"q": "Is it good?", "a": "Yes"}],
    )
    raw = asdict(dto)
    assert raw["url"] == "https://walmart.com/bar"
    assert raw["title"] == "Test Product"
    assert raw["price"] == "$19.99"
    assert raw["original_price"] == "$29.99"
    assert raw["rating"] == "4.5"
    assert raw["review_count"] == "1234"
    assert raw["bullet_points"] == ["Feature A", "Feature B"]
    assert raw["attributes"] == {"Color": "Red", "Size": "M"}
    assert raw["description"] == "A great product."


def test_hypothesis_dto_defaults():
    dto = HypothesisDTO()
    assert dto.direction_name == ""
    assert dto.estimated_score == 0.0
    assert dto.thumbnail_visible is True
    assert dto.keywords == {}


def test_hypothesis_dto_asdict():
    dto = HypothesisDTO(
        direction_name="Test Direction",
        category_type="complement",
        motivation_type="pain_point",
        estimated_score=85.5,
        keywords={"en": "test keyword", "amazon": "test keyword"},
    )
    raw = asdict(dto)
    assert raw["direction_name"] == "Test Direction"
    assert raw["estimated_score"] == 85.5
    assert raw["keywords"] == {"en": "test keyword", "amazon": "test keyword"}


def test_direction_dto():
    hypothesis = HypothesisDTO(direction_name="Test", estimated_score=75.0)
    direction = DirectionDTO(
        hypothesis=hypothesis,
        deep_arguments={"user_rationale": "It makes sense"},
        delivery_checklist={"bundling_display": "Bundle"},
    )
    assert direction.hypothesis.direction_name == "Test"
    assert direction.deep_arguments["user_rationale"] == "It makes sense"
    assert direction.delivery_checklist["bundling_display"] == "Bundle"

    raw = asdict(direction)
    assert raw["hypothesis"]["direction_name"] == "Test"
    assert raw["deep_arguments"]["user_rationale"] == "It makes sense"


def test_hypothesis_result_dto():
    product = ProductDTO(url="https://walmart.com/p", title="Product X")
    result = HypothesisResultDTO(product=product)
    result.product_analysis = {"title": "Product X", "price": "$10"}
    result.evidence_table = {"first_layer": {}, "second_layer": {}, "third_layer": {}}
    result.strategic_judgment = {"type": "low_cost_value_add"}
    result.directions = [
        DirectionDTO(
            hypothesis=HypothesisDTO(direction_name="Dir 1", estimated_score=80.0),
            deep_arguments={},
            delivery_checklist={},
        )
    ]
    result.keyword_pack = ["kw1", "kw2"]

    raw = asdict(result)
    assert raw["product"]["url"] == "https://walmart.com/p"
    assert len(raw["directions"]) == 1
    assert raw["directions"][0]["hypothesis"]["direction_name"] == "Dir 1"
    assert raw["keyword_pack"] == ["kw1", "kw2"]


def test_judgment_result_dto():
    dto = JudgmentResultDTO()
    dto.alignment_review = [{"product_b": "B1", "overall_verdict": "alignment"}]
    dto.motivation_review = {"per_b_product": {}}
    dto.price_calculation = {"per_b_product": {}}
    dto.veto_check = {"per_b_product": {}}
    dto.c_score = {"per_b_product": {"B1": {"total": 85}}}
    dto.b_score = {"per_b_product": {"B1": {"total": 70}}}
    dto.final_grade = "A"
    dto.delivery_package = {"per_b_product": {}}
    dto.priority_score = 1.0

    raw = asdict(dto)
    assert raw["final_grade"] == "A"
    assert raw["priority_score"] == 1.0
    assert len(raw["alignment_review"]) == 1


def test_judgment_result_defaults():
    dto = JudgmentResultDTO()
    assert dto.alignment_review == []
    assert dto.final_grade == ""
    assert dto.priority_score == 0.0
