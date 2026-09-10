from __future__ import annotations

import os
import subprocess

EXPECTED_COMBINATION_MODEL_VERSION = "combination_model_v2.1"
REVISION_ENV = "APP_REVISION"


def runtime_revision() -> str:
    configured = os.getenv(REVISION_ENV, "").strip()
    if configured:
        return configured
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
            or "unknown"
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"


__all__ = ["EXPECTED_COMBINATION_MODEL_VERSION", "REVISION_ENV", "runtime_revision"]
