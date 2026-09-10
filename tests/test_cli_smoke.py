from __future__ import annotations

import sys
from unittest.mock import AsyncMock

import pytest

import app.main as main_module


def test_generate_mode_dispatches_existing_runner(monkeypatch):
    runner = AsyncMock()
    monkeypatch.setattr(main_module, "run_generate", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        ["bundling", "--mode", "generate", "--url", "https://walmart.com/ip/a/1"],
    )

    main_module.main()

    runner.assert_awaited_once_with("https://walmart.com/ip/a/1")


def test_judge_mode_dispatches_existing_runner(monkeypatch):
    runner = AsyncMock()
    monkeypatch.setattr(main_module, "run_judge", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bundling",
            "--mode",
            "judge",
            "--a-url",
            "https://walmart.com/ip/a/1",
            "--b-urls",
            "https://amazon.com/dp/B000000001",
            "https://amazon.com/dp/B000000002",
        ],
    )

    main_module.main()

    runner.assert_awaited_once_with(
        "https://walmart.com/ip/a/1",
        [
            "https://amazon.com/dp/B000000001",
            "https://amazon.com/dp/B000000002",
        ],
    )


def test_batch_resume_dispatches_existing_runner(monkeypatch):
    runner = AsyncMock()
    monkeypatch.setattr(main_module, "run_batch", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        ["bundling", "--mode", "batch", "--resume", "batch-1"],
    )

    main_module.main()

    runner.assert_awaited_once_with(None, "batch-1")


def test_generate_mode_still_requires_url(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bundling", "--mode", "generate"])

    with pytest.raises(SystemExit) as error:
        main_module.main()

    assert error.value.code == 2
