from __future__ import annotations

import json

from app.domain.dto import HypothesisResultDTO
from app.infrastructure.storage import BundleResultStore


def test_result_filenames_are_unique(tmp_path):
    store = BundleResultStore(tmp_path)

    first = store.save_hypothesis(HypothesisResultDTO())
    second = store.save_hypothesis(HypothesisResultDTO())

    assert first != second
    assert first.exists()
    assert second.exists()


def test_saved_hypothesis_contains_v2_profile(tmp_path):
    result = HypothesisResultDTO(
        model_version="combination_model_v2.0",
        product_profile={"core_purchase_job": "print"},
    )

    path = BundleResultStore(tmp_path).save_hypothesis(result)
    payload = path.read_text(encoding="utf-8")

    assert '"model_version": "combination_model_v2.0"' in payload
    assert '"product_profile": {' in payload


def test_saved_hypothesis_includes_result_quality_audit_fields(tmp_path):
    result = HypothesisResultDTO(
        model_version="combination_model_v2.1",
        result_status="completed_no_qualified_candidates",
        result_message="No qualified candidates",
        rejection_summary={"food": 2},
        audit_performed=True,
        audit_reason="initial_v2.1_directions_empty",
        audit_outcome="confirmed_no_candidates",
        provider="custom",
        provider_model="claude-test",
    )

    path = BundleResultStore(tmp_path).save_hypothesis(result)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["result_status"] == "completed_no_qualified_candidates"
    assert payload["rejection_summary"] == {"food": 2}
    assert payload["audit_outcome"] == "confirmed_no_candidates"
    assert payload["provider_model"] == "claude-test"
