from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.core.runtime_contract import (
    EXPECTED_COMBINATION_MODEL_VERSION,
    runtime_revision,
)


def write_local_worker_identity(path: Path, worker_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    payload = {
        "worker_id": worker_id,
        "model_version": EXPECTED_COMBINATION_MODEL_VERSION,
        "revision": runtime_revision(),
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


def read_local_worker_identity(path: Path) -> dict[str, str] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


__all__ = ["read_local_worker_identity", "write_local_worker_identity"]
