from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from app.core.exceptions import ModelContractError
from app.core.runtime_contract import (
    EXPECTED_COMBINATION_MODEL_VERSION,
    runtime_revision,
)


def test_runtime_revision_prefers_build_environment(monkeypatch):
    monkeypatch.setenv("APP_REVISION", " release-abc123 ")

    with patch("app.core.runtime_contract.subprocess.run") as run:
        revision = runtime_revision()

    assert revision == "release-abc123"
    run.assert_not_called()


def test_runtime_revision_uses_short_git_revision(monkeypatch):
    monkeypatch.delenv("APP_REVISION", raising=False)

    with patch(
        "app.core.runtime_contract.subprocess.run",
        return_value=SimpleNamespace(stdout="abc1234\n"),
    ) as run:
        revision = runtime_revision()

    assert revision == "abc1234"
    run.assert_called_once_with(
        ["git", "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )


def test_runtime_revision_falls_back_when_git_is_unavailable(monkeypatch):
    monkeypatch.delenv("APP_REVISION", raising=False)

    with patch(
        "app.core.runtime_contract.subprocess.run",
        side_effect=subprocess.TimeoutExpired("git", 2),
    ):
        assert runtime_revision() == "unknown"


def test_model_contract_error_is_stable_and_not_retryable():
    error = ModelContractError(
        expected=EXPECTED_COMBINATION_MODEL_VERSION,
        actual="combination_model_v2.0",
    )

    assert error.code == "MODEL_CONTRACT_MISMATCH"
    assert error.retryable is False
    assert "Restart the API and Worker" in error.message
