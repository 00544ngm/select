"""Checkpoint / resume mechanism for batch processing."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class CheckpointManager:
    """Tracks batch processing progress so it can resume after interruption.

    The checkpoint file is a JSON file that records each URL's status.
    """

    def __init__(self, batch_id: str, checkpoint_dir: str | Path = "output/checkpoints") -> None:
        self._dir = Path(checkpoint_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{batch_id}.json"
        self._state: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text(encoding="utf-8"))
        return {"batch_id": self._path.stem, "created_at": datetime.now().isoformat(),
                "updated_at": "", "urls": {}, "stats": {"total": 0, "done": 0, "failed": 0, "pending": 0}}

    def _save(self) -> None:
        self._state["updated_at"] = datetime.now().isoformat()
        st = self._state["stats"]
        urls = self._state["urls"]
        st["total"] = len(urls)
        st["done"] = sum(1 for u in urls.values() if u["status"] == "done")
        st["failed"] = sum(1 for u in urls.values() if u["status"] == "failed")
        st["pending"] = sum(1 for u in urls.values() if u["status"] == "pending")
        temporary_path = self._path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self._path)

    def add_urls(self, urls: list[str]) -> None:
        """Register URLs for processing. Existing URLs are not overwritten."""
        for url in urls:
            if url not in self._state["urls"]:
                self._state["urls"][url] = {"status": "pending", "output": "", "error": ""}
        self._save()

    def mark_done(self, url: str, output_path: str = "") -> None:
        if url in self._state["urls"]:
            self._state["urls"][url]["status"] = "done"
            self._state["urls"][url]["output"] = output_path
            self._save()

    def mark_failed(self, url: str, error: str = "") -> None:
        if url in self._state["urls"]:
            self._state["urls"][url]["status"] = "failed"
            self._state["urls"][url]["error"] = error
            self._save()

    def mark_pending(self, url: str) -> None:
        if url in self._state["urls"]:
            self._state["urls"][url] = {
                "status": "pending",
                "output": "",
                "error": "",
            }
            self._save()

    def get_pending(self) -> list[str]:
        return [url for url, info in self._state["urls"].items()
                if info["status"] == "pending"]

    def get_retryable(self) -> list[str]:
        return [
            url
            for url, info in self._state["urls"].items()
            if info["status"] in {"pending", "failed"}
        ]

    @property
    def stats(self) -> dict:
        return dict(self._state["stats"])

    @property
    def summary(self) -> str:
        s = self.stats
        return f"Done: {s['done']}, Failed: {s['failed']}, Pending: {s['pending']}, Total: {s['total']}"

    @classmethod
    def load(cls, batch_id: str, checkpoint_dir: str | Path = "output/checkpoints") -> CheckpointManager:
        """Load an existing checkpoint. Raises FileNotFoundError if not found."""
        path = Path(checkpoint_dir) / f"{batch_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")
        mgr = cls.__new__(cls)
        mgr._dir = Path(checkpoint_dir)
        mgr._path = path
        mgr._state = mgr._load()
        return mgr


__all__ = ["CheckpointManager"]
