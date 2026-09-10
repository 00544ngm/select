"""Maike gpt 专属执行上限的单元测试。

背景：Maike 中转（provider slug `custom`）的 OpenAI 兼容 gpt 通道对真实完整
请求很慢（约 5 分钟）且首试常被上游判不可用，需要在受控自动重试后再给一次约
5 分钟窗口；因此该组合放宽到 1000s，其它通道维持 600s 不变。
"""

from __future__ import annotations

from backend.workers.jobs import _resolve_job_deadline

_MAIKE_GPT = 1000.0
_STANDARD = 600.0


def test_standard_providers_keep_600_second_deadline() -> None:
    # OpenAI 官方、DeepSeek、Maike Anthropic 通道不受影响
    assert _resolve_job_deadline("openai", "gpt-5.6-terra") == _STANDARD
    assert _resolve_job_deadline("deepseek", "deepseek-v4-flash") == _STANDARD
    assert _resolve_job_deadline("claude", "claude-opus-5") == _STANDARD
    # 未显式指定 provider 或 model 时维持原状
    assert _resolve_job_deadline(None, "gpt-5.5") == _STANDARD
    assert _resolve_job_deadline("custom", None) == _STANDARD
    assert _resolve_job_deadline(None, None) == _STANDARD


def test_maike_gpt_models_get_relaxed_deadline() -> None:
    assert _resolve_job_deadline("custom", "gpt-5.6-terra") == _MAIKE_GPT
    assert _resolve_job_deadline("custom", "gpt-5.6-sol") == _MAIKE_GPT
    assert _resolve_job_deadline("custom", "gpt-5.5") == _MAIKE_GPT
    # 大小写不敏感
    assert _resolve_job_deadline("custom", " GPT-5.6-TERRA ") == _MAIKE_GPT


def test_maike_non_gpt_models_keep_standard_deadline() -> None:
    assert _resolve_job_deadline("custom", "claude-sonnet-4-6") == _STANDARD
