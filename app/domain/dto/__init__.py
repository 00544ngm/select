from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


class DirectionProductTypeEvidence(TypedDict):
    source_field: Literal["name_zh", "name_en", "canonical_name"]
    verbatim_quote: str


class DirectionProductTypeReview(TypedDict):
    status: Literal[
        "confirmed_non_food", "confirmed_food", "likely_non_food", "needs_review"
    ]
    source: Literal["rule", "model", "fallback"]
    confidence: float
    reason: str
    evidence: list[DirectionProductTypeEvidence]
    action: Literal["continue", "continue_with_review", "block"]


@dataclass
class ProductDTO:
    """Walmart product details from scraping."""
    url: str = ""
    product_id: str | None = None
    title: str = ""
    price: str = ""
    original_price: str | None = None
    rating: str = ""
    review_count: str = ""
    bullet_points: list[str] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    description: str | None = None
    fbt_items: list[dict] = field(default_factory=list)
    review_snippets: list[str] = field(default_factory=list)
    qa_pairs: list[dict] = field(default_factory=list)


@dataclass
class HypothesisDTO:
    """Single B-candidate hypothesis direction."""
    direction_name: str = ""
    category_type: str = ""
    motivation_type: str = ""
    motivation_evidence: str = ""
    evidence_level: str = ""
    estimated_cost_1688: str = ""
    price_strategy: str = ""
    thumbnail_visible: bool = True
    stickiness: str = ""
    estimated_score: float = 0.0
    keywords: dict[str, str] = field(default_factory=dict)
    model_version: str = "combination_model_v2.0"
    canonical_name: str = ""
    primary_relation: str = ""
    secondary_relations: list[str] = field(default_factory=list)
    purchase_chain: dict[str, str] = field(default_factory=dict)
    lifecycle_stage: str = ""
    consistency: dict[str, Any] = field(default_factory=dict)
    consumer_simulation: str = ""
    consumer_simulation_reason: str = ""
    score_breakdown: dict[str, float] = field(default_factory=dict)
    score_inputs: dict[str, int] = field(default_factory=dict)
    raw_score: float = 0.0
    score_cap: int = 0
    final_score: float = 0.0
    recommendation_level: str = "not_recommended"
    evidence: dict[str, Any] = field(default_factory=dict)
    rejected: bool = False
    rejection_codes: list[str] = field(default_factory=list)
    invalid_source_fact_ids: list[str] = field(default_factory=list)
    source_fact_ids: list[str] = field(default_factory=list)
    incompatibility_reason: str = ""
    duplicate_function_reason: str = ""
    safety_risk: str = ""
    risk_analysis: str = ""
    missing_evidence: list[str] = field(default_factory=list)
    food_filter_status: str = "needs_verification"
    food_filter_reason: str = ""
    relation_reasons: list[str] = field(default_factory=list)
    extended_scenarios: list[dict[str, str]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    confidence_level: str = "low"
    purchase_direction: str = "none"
    direction_reason: str = ""
    product_type_status: str = "unknown"
    product_type_review: DirectionProductTypeReview | None = None
    compatibility_status: str = "needs_verification"
    duplication_status: str = "needs_verification"
    safety_status: str = "needs_verification"
    execution_status: str = "pass"
    hold_reasons: list[str] = field(default_factory=list)
    decision_action: str = "not_recommended"
    stickiness_score: float = 0.0


@dataclass
class DirectionDTO:
    """Full direction with deep arguments and delivery checklist."""
    hypothesis: HypothesisDTO = field(default_factory=HypothesisDTO)
    deep_arguments: dict[str, Any] = field(default_factory=dict)
    delivery_checklist: dict[str, Any] = field(default_factory=dict)


@dataclass
class HypothesisResultDTO:
    """Complete output of instruction A (hypothesis generation)."""
    product: ProductDTO = field(default_factory=ProductDTO)
    product_analysis: dict[str, Any] = field(default_factory=dict)
    evidence_table: dict[str, Any] = field(default_factory=dict)
    strategic_judgment: dict[str, str] = field(default_factory=dict)
    directions: list[DirectionDTO] = field(default_factory=list)
    keyword_pack: list[str] = field(default_factory=list)
    model_version: str = "combination_model_v2.0"
    product_profile: dict[str, Any] = field(default_factory=dict)
    result_status: str = ""
    result_message: str = ""
    raw_direction_count: int = 0
    qualified_direction_count: int = 0
    hold_direction_count: int = 0
    rejected_direction_count: int = 0
    rejection_summary: dict[str, int] = field(default_factory=dict)
    audit_performed: bool = False
    audit_reason: str = ""
    initial_raw_direction_count: int = 0
    audit_raw_direction_count: int = 0
    audit_outcome: str = ""
    provider: str = ""
    provider_model: str = ""


@dataclass
class JudgmentResultDTO:
    """Complete output of instruction B (hypothesis judgment)."""
    alignment_review: list[dict] = field(default_factory=list)
    motivation_review: dict[str, Any] = field(default_factory=dict)
    price_calculation: dict[str, Any] = field(default_factory=dict)
    veto_check: dict[str, str] = field(default_factory=dict)
    c_score: dict[str, Any] = field(default_factory=dict)
    b_score: dict[str, Any] = field(default_factory=dict)
    final_grade: str = ""
    delivery_package: dict[str, Any] = field(default_factory=dict)
    priority_score: float = 0.0
    product_title_zh: str = ""
    user_rationality: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "DirectionDTO",
    "DirectionProductTypeEvidence",
    "DirectionProductTypeReview",
    "HypothesisDTO",
    "HypothesisResultDTO",
    "JudgmentResultDTO",
    "ProductDTO",
]
