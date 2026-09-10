from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class PurchaseDirection(StrEnum):
    FORWARD_DEPENDENCY = "forward_dependency"
    BIDIRECTIONAL = "bidirectional"
    REVERSE_DEPENDENCY = "reverse_dependency"
    NONE = "none"


class ProductTypeStatus(StrEnum):
    INGESTIBLE = "ingestible"
    FOOD = "food"
    NON_FOOD = "non_food"
    UNKNOWN = "unknown"


class GateAssessment(StrEnum):
    CLEAR = "clear"
    NEEDS_VERIFICATION = "needs_verification"
    BLOCKED = "blocked"


class ExecutionStatus(StrEnum):
    PASS = "pass"
    HOLD = "hold"
    REJECT = "reject"


class DecisionAction(StrEnum):
    NOT_RECOMMENDED = "not_recommended"
    OBSERVE = "observe"
    NEEDS_EVIDENCE = "needs_evidence"
    SMALL_BATCH_TEST = "small_batch_test"
    PRIORITY_TEST = "priority_test"
    FOCUS_DEVELOPMENT = "focus_development"


@dataclass(frozen=True)
class RelationshipScoreCaps:
    function_necessity: int
    usage_continuity: int
    purchase_direction: int
    natural_copurchase: int
    enhancement_maintenance: int
    scene_fit: int


RELATIONSHIP_SCORE_CAPS: Mapping[str, RelationshipScoreCaps] = MappingProxyType(
    {
        "required_dependency": RelationshipScoreCaps(5, 5, 5, 5, 5, 5),
        "spec_compatibility": RelationshipScoreCaps(5, 4, 5, 5, 4, 5),
        "consumable_refill": RelationshipScoreCaps(5, 4, 5, 5, 5, 5),
        "continuous_task": RelationshipScoreCaps(4, 5, 5, 4, 4, 5),
        "protection_maintenance": RelationshipScoreCaps(4, 4, 4, 4, 5, 5),
        "effect_enhancement": RelationshipScoreCaps(4, 4, 4, 3, 5, 5),
        "storage_transport": RelationshipScoreCaps(3, 4, 4, 3, 4, 5),
        "style_occasion": RelationshipScoreCaps(2, 3, 3, 2, 3, 5),
    }
)


__all__ = [
    "RELATIONSHIP_SCORE_CAPS",
    "DecisionAction",
    "ExecutionStatus",
    "ProductTypeStatus",
    "PurchaseDirection",
    "RelationshipScoreCaps",
]
