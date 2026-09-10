from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Any

from app.core.runtime_contract import (
    EXPECTED_COMBINATION_MODEL_VERSION,
    runtime_revision,
)

WORKER_IDENTITY_KEY = "bundling:worker:runtime-identity"
WORKER_IDENTITY_TTL_SECONDS = 30


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def refresh_worker_identity(ctx: dict[str, Any]) -> None:
    identity = {
        "model_version": EXPECTED_COMBINATION_MODEL_VERSION,
        "revision": runtime_revision(),
        "started_at": ctx.setdefault("worker_started_at", _utc_now_iso()),
        "worker_id": ctx.setdefault(
            "worker_id", f"{socket.gethostname()}:{os.getpid()}"
        ),
    }
    await ctx["redis"].set(
        WORKER_IDENTITY_KEY,
        json.dumps(identity),
        ex=WORKER_IDENTITY_TTL_SECONDS,
    )


__all__ = [
    "WORKER_IDENTITY_KEY",
    "WORKER_IDENTITY_TTL_SECONDS",
    "refresh_worker_identity",
]
