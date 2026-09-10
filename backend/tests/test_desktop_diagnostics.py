from __future__ import annotations

import json

import pytest

from backend.desktop.diagnostics import run_desktop_diagnostics
from backend.desktop.paths import DesktopPaths


@pytest.mark.asyncio
async def test_diagnostics_reports_writable_paths_and_browser_success(tmp_path):
    paths = DesktopPaths(data_dir=tmp_path / "员工 #100% 空格")

    async def browser_probe():
        return None

    payload = await run_desktop_diagnostics(paths=paths, browser_probe=browser_probe)

    assert payload["checks"]["runtime_paths"]["status"] == "passed"
    assert payload["checks"]["browser"]["status"] == "passed"
    assert payload["checks"]["windows_security"]["status"] == "manual_check"
    assert "api_key" not in json.dumps(payload).lower()


@pytest.mark.asyncio
async def test_diagnostics_reports_browser_start_failure_without_exposing_path(tmp_path):
    paths = DesktopPaths(data_dir=tmp_path / "employee")

    async def browser_probe():
        raise RuntimeError("secret-local-path chrome exited")

    payload = await run_desktop_diagnostics(paths=paths, browser_probe=browser_probe)

    check = payload["checks"]["browser"]
    assert check["status"] == "failed"
    assert check["code"] == "DESKTOP_BROWSER_START_FAILED"
    assert "secret-local-path" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_diagnostics_reports_selected_browser_and_fallback_attempts(tmp_path):
    paths = DesktopPaths(data_dir=tmp_path / "employee")

    async def browser_probe():
        return {
            "selected": "bundled_chromium",
            "attempts": [
                {"browser": "edge", "status": "failed"},
                {"browser": "bundled_chromium", "status": "passed"},
            ],
        }

    payload = await run_desktop_diagnostics(paths=paths, browser_probe=browser_probe)

    check = payload["checks"]["browser"]
    assert check["status"] == "passed"
    assert check["selected"] == "bundled_chromium"
    assert check["attempts"][0] == {"browser": "edge", "status": "failed"}
