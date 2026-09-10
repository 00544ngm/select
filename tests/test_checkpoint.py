from __future__ import annotations

import pytest

from app.infrastructure.storage.checkpoint import CheckpointManager
from app.main import run_batch


def test_retryable_urls_include_failed_entries(tmp_path):
    checkpoint = CheckpointManager("batch-1", tmp_path)
    url = "https://walmart.com/ip/example/12345"
    checkpoint.add_urls([url])
    checkpoint.mark_failed(url, "timeout")

    assert checkpoint.get_retryable() == [url]


def test_mark_pending_clears_previous_result(tmp_path):
    checkpoint = CheckpointManager("batch-2", tmp_path)
    url = "https://walmart.com/ip/example/12345"
    checkpoint.add_urls([url])
    checkpoint.mark_done(url, "old-result.json")
    checkpoint.mark_failed(url, "timeout")

    checkpoint.mark_pending(url)

    assert checkpoint._state["urls"][url] == {
        "status": "pending",
        "output": "",
        "error": "",
    }


def test_checkpoint_save_replaces_temporary_file(tmp_path):
    checkpoint = CheckpointManager("batch-3", tmp_path)

    checkpoint.add_urls(["https://walmart.com/ip/example/12345"])

    assert checkpoint._path.exists()
    assert not checkpoint._path.with_suffix(".tmp").exists()


@pytest.mark.asyncio
async def test_resume_reads_retryable_urls(monkeypatch):
    class FakeCheckpoint:
        retryable_called = False
        summary = "Done: 0, Failed: 1, Pending: 0, Total: 1"

        def get_pending(self):
            return []

        def get_retryable(self):
            self.retryable_called = True
            return []

    checkpoint = FakeCheckpoint()
    monkeypatch.setattr(
        "app.main.CheckpointManager.load", lambda batch_id: checkpoint
    )

    await run_batch("", "batch-1")

    assert checkpoint.retryable_called is True
