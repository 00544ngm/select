from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.pairing_policy import GateAssessment

RelationType = Literal[
    "required_dependency",
    "spec_compatibility",
    "consumable_refill",
    "continuous_task",
    "protection_maintenance",
    "effect_enhancement",
    "storage_transport",
    "style_occasion",
    "weak_context",
    "none",
]
LifecycleStage = Literal[
    "purchase",
    "setup",
    "use",
    "enhance",
    "protect_maintain",
    "storage_transport",
    "replenish",
    "repurchase",
]
FoodFilterStatus = Literal["food", "allowed", "needs_verification"]
PurchaseDirection = Literal["forward_dependency", "bidirectional", "reverse_dependency", "none"]
ProductTypeStatus = Literal["food", "non_food", "unknown"]


class RatedReason(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: int = Field(ge=0, le=5)
    reason: str = Field(min_length=1)


class ConsistencyOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user: RatedReason
    scenario: RatedReason
    lifecycle: RatedReason
    mental: RatedReason


class IndependentRatingsOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    relation_strength: int = Field(ge=0, le=5)
    repeat_value: int = Field(ge=0, le=5)
    function_gain: int = Field(ge=0, le=5)


class IncludedItemOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    canonical_name: str = Field(min_length=1)
    source_fact_ids: list[str] = Field(default_factory=list)


class ProductProfileOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title_zh: str = Field(min_length=1)
    core_purchase_job: str = Field(min_length=1)
    lifecycle_steps: list[str] = Field(default_factory=list)
    included_items: list[IncludedItemOutput] = Field(default_factory=list)
    compatibility_constraints: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    primary_search_terms: list[str] = Field(default_factory=list)
    source_url: str = ""
    product_type: str = ""
    source_collected_at: str = ""


class ExtendedScenarioOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    assumption: str = ""
    reason: str = ""


class HypothesisDirectionOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name_zh: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    primary_relation: RelationType
    purchase_direction: PurchaseDirection = "none"
    direction_reason: str = ""
    product_type_status: ProductTypeStatus = "unknown"
    compatibility_status: GateAssessment = GateAssessment.NEEDS_VERIFICATION
    duplication_status: GateAssessment = GateAssessment.NEEDS_VERIFICATION
    safety_status: GateAssessment = GateAssessment.NEEDS_VERIFICATION
    risk_categories: list[str] = Field(default_factory=list)
    secondary_relations: list[RelationType] = Field(default_factory=list)
    purchase_chain: dict[str, str] = Field(default_factory=dict)
    lifecycle_stage: LifecycleStage
    consistency: ConsistencyOutput
    consumer_simulation: Literal["A", "B", "C", "D"]
    consumer_simulation_reason: str = Field(min_length=1)
    independent_ratings: IndependentRatingsOutput
    source_fact_ids: list[str] = Field(default_factory=list)
    incompatibility_reason: str = ""
    duplicate_function_reason: str = ""
    safety_risk: str = ""
    risk_analysis: str = ""
    missing_evidence: list[str] = Field(default_factory=list)
    keywords: dict[str, str] = Field(default_factory=dict)
    estimated_cost_1688: str = ""
    price_strategy: str = ""
    delivery_checklist: dict[str, Any] = Field(default_factory=dict)
    food_filter_status: FoodFilterStatus = "needs_verification"
    food_filter_reason: str = ""
    relation_reasons: list[str] = Field(default_factory=list)
    extended_scenarios: list[ExtendedScenarioOutput] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence_level: Literal["high", "medium", "low"] = "low"

class HypothesisOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model_version: Literal["combination_model_v2.0", "combination_model_v2.1"]
    product_profile: ProductProfileOutput
    directions: list[HypothesisDirectionOutput] = Field(default_factory=list, max_length=12)
    keyword_pack: list[str] = Field(default_factory=list)


__all__ = [
    "ConsistencyOutput",
    "ExtendedScenarioOutput",
    "FoodFilterStatus",
    "HypothesisDirectionOutput",
    "HypothesisOutput",
    "IncludedItemOutput",
    "IndependentRatingsOutput",
    "LifecycleStage",
    "ProductProfileOutput",
    "RatedReason",
    "RelationType",
]
