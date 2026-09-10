from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.exceptions import BrowserError
from app.infrastructure.browser import (
    PlaywrightBrowserManager,
    build_chrome_launch_args,
)
from backend.desktop.browser_paths import BrowserCandidate


def test_chrome_launch_args_do_not_disable_security_boundaries(tmp_path):
    args = build_chrome_launch_args(tmp_path / "profile")

    assert "--no-sandbox" not in args
    assert "--remote-allow-origins=*" not in args


@pytest.mark.asyncio
async def test_stop_terminates_manager_owned_chrome_process():
    manager = PlaywrightBrowserManager()
    process = Mock()
    process.wait.return_value = 0
    playwright = AsyncMock()
    manager._chrome_process = process
    manager._owns_chrome_process = True
    manager._playwright = playwright

    await manager.stop()

    playwright.stop.assert_awaited_once()
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)


@pytest.mark.asyncio
async def test_stop_leaves_external_chrome_process_running():
    manager = PlaywrightBrowserManager()
    process = Mock()
    manager._chrome_process = process
    manager._owns_chrome_process = False
    manager._playwright = AsyncMock()

    await manager.stop()

    process.terminate.assert_not_called()
    process.kill.assert_not_called()


@pytest.mark.asyncio
async def test_stop_continues_cleanup_after_disconnected_context():
    manager = PlaywrightBrowserManager()
    context = AsyncMock()
    context.close.side_effect = RuntimeError("target already closed")
    browser = AsyncMock()
    playwright = AsyncMock()
    manager._context = context
    manager._browser = browser
    manager._playwright = playwright

    with pytest.raises(BrowserError, match="target already closed"):
        await manager.stop()

    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_suppresses_stale_cleanup_error_and_starts_fresh_browser():
    manager = PlaywrightBrowserManager()
    manager.stop = AsyncMock()
    manager.start = AsyncMock()

    await manager.restart()

    manager.stop.assert_awaited_once_with(raise_errors=False)
    manager.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_desktop_start_falls_back_from_edge_to_bundled_chromium(monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    bundled_browser = AsyncMock()
    bundled_browser.new_context = AsyncMock(return_value=AsyncMock())
    chromium = Mock()
    chromium.launch = AsyncMock(
        side_effect=[RuntimeError("edge terminated"), bundled_browser]
    )
    playwright = SimpleNamespace(chromium=chromium)
    manager = PlaywrightBrowserManager()

    with (
        patch("app.infrastructure.browser.async_playwright") as async_playwright,
        patch(
            "app.infrastructure.browser.resolve_browser_candidates",
            return_value=[
                BrowserCandidate("edge", Path("C:/Edge/msedge.exe")),
                BrowserCandidate(
                    "bundled_chromium", Path("C:/App/browser/chrome.exe")
                ),
            ],
        ),
    ):
        async_playwright.return_value.start = AsyncMock(return_value=playwright)
        await manager.start()

    assert chromium.launch.await_count == 2
    assert manager.selected_browser_kind == "bundled_chromium"


@pytest.mark.asyncio
async def test_desktop_start_falls_back_when_failed_edge_cleanup_also_fails(monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    failed_edge = AsyncMock()
    failed_edge.new_context.side_effect = RuntimeError("edge context terminated")
    failed_edge.close.side_effect = RuntimeError("edge already closed")
    bundled_browser = AsyncMock()
    bundled_browser.new_context = AsyncMock(return_value=AsyncMock())
    chromium = Mock()
    chromium.launch = AsyncMock(side_effect=[failed_edge, bundled_browser])
    playwright = SimpleNamespace(chromium=chromium)
    manager = PlaywrightBrowserManager()

    with (
        patch("app.infrastructure.browser.async_playwright") as async_playwright,
        patch(
            "app.infrastructure.browser.resolve_browser_candidates",
            return_value=[
                BrowserCandidate("edge", Path("C:/Edge/msedge.exe")),
                BrowserCandidate(
                    "bundled_chromium", Path("C:/App/browser/chrome.exe")
                ),
            ],
        ),
    ):
        async_playwright.return_value.start = AsyncMock(return_value=playwright)
        await manager.start()

    assert chromium.launch.await_count == 2
    assert manager.selected_browser_kind == "bundled_chromium"


@pytest.mark.asyncio
async def test_desktop_start_stops_playwright_when_no_browser_candidate(monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    playwright = SimpleNamespace(chromium=Mock(), stop=AsyncMock())
    manager = PlaywrightBrowserManager()

    with (
        patch("app.infrastructure.browser.async_playwright") as async_playwright,
        patch(
            "app.infrastructure.browser.resolve_browser_candidates",
            side_effect=RuntimeError("DESKTOP_BROWSER_MISSING"),
        ),
    ):
        async_playwright.return_value.start = AsyncMock(return_value=playwright)
        with pytest.raises(RuntimeError, match="DESKTOP_BROWSER_MISSING"):
            await manager.start()

    playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_prefers_bundled_after_running_edge_closes(monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    manager = PlaywrightBrowserManager()
    manager._selected_browser_kind = "edge"
    manager.stop = AsyncMock()
    manager.start = AsyncMock()

    await manager.restart()

    assert manager._avoid_browser_kind_once == "edge"
    manager.stop.assert_awaited_once_with(raise_errors=False)
    manager.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_visible_relaunches_browser_in_headful_mode(monkeypatch):
    monkeypatch.setenv("RUNTIME_MODE", "desktop")
    bundled_browser = AsyncMock()
    bundled_browser.new_context = AsyncMock(return_value=AsyncMock())
    chromium = Mock()
    chromium.launch = AsyncMock(return_value=bundled_browser)
    playwright = SimpleNamespace(chromium=chromium)
    manager = PlaywrightBrowserManager()

    with (
        patch("app.infrastructure.browser.async_playwright") as async_playwright,
        patch(
            "app.infrastructure.browser.resolve_browser_candidates",
            return_value=[
                BrowserCandidate(
                    "bundled_chromium", Path("C:/App/browser/chrome.exe")
                )
            ],
        ),
    ):
        async_playwright.return_value.start = AsyncMock(return_value=playwright)
        await manager.restart_visible()

    assert chromium.launch.await_args.kwargs["headless"] is False
