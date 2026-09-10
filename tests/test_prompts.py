"""Tests for prompt template file existence and content."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).parent.parent / "app" / "infrastructure" / "llm" / "prompts"


def test_hypothesis_prompt_exists():
    path = PROMPT_DIR / "hypothesis_a.txt"
    assert path.exists(), f"Missing: {path}"
    content = path.read_text(encoding="utf-8")
    assert "{product_url}" in content
    assert "{product_data}" in content
    assert "directions" in content


def test_judgment_prompt_exists():
    path = PROMPT_DIR / "judgment_b.txt"
    assert path.exists(), f"Missing: {path}"
    content = path.read_text(encoding="utf-8")
    assert "{product_a_data}" in content
    assert "{product_b_data}" in content
    assert "{original_hypotheses}" in content
    assert "final_grade" in content
    assert "product_title_zh" in content


def test_hypothesis_prompt_has_required_sections():
    content = (PROMPT_DIR / "hypothesis_a.txt").read_text(encoding="utf-8")
    assert "product_profile" in content
    assert "core_purchase_job" in content
    assert "lifecycle_steps" in content
    assert "directions" in content
    assert "keyword_pack" in content
    assert "source_fact_ids" in content
    assert "consumer_simulation" in content


def test_hypothesis_prompt_restricts_secondary_relations_to_schema_values():
    content = (PROMPT_DIR / "hypothesis_a.txt").read_text(encoding="utf-8")
    assert (
        "secondary_relations 只能从上述【允许的主要关系】英文枚举中选择"
        in content
    )


def test_hypothesis_prompt_does_not_force_a_fixed_direction_quota_or_score():
    content = (PROMPT_DIR / "hypothesis_a.txt").read_text(encoding="utf-8")
    assert "8-10" not in content
    assert "estimated_score" not in content


def test_hypothesis_prompt_requires_three_state_gate_evidence():
    content = (PROMPT_DIR / "hypothesis_a.txt").read_text(encoding="utf-8")
    assert "blocked 必须有确认阻断事实" in content
    assert "信息不足只能使用 needs_verification" in content


def test_hypothesis_prompt_requires_one_precise_and_one_generic_keyword():
    content = (PROMPT_DIR / "hypothesis_a.txt").read_text(encoding="utf-8")
    assert "keywords.amazon：只输出 1 条 Amazon 精准检索短语" in content
    assert "keywords.en：只输出 1 条英文通用扩展短语" in content
    assert "禁止加入 amazon、促销词、无依据品牌词" in content


def test_judgment_prompt_has_six_gates():
    content = (PROMPT_DIR / "judgment_b.txt").read_text(encoding="utf-8")
    assert "Alignment Review" in content
    assert "Motivation Review" in content
    assert "Price Calculation" in content
    assert "Veto Check" in content
    assert "C-Score" in content or "C_score" in content
    assert "Final Grade" in content or "final_grade" in content
