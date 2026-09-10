from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from app.core.config import settings
from app.core.exceptions import BrowserError, BrowserTargetClosedError
from app.core.logger import logger
from app.domain.interfaces import BrowserManager as BrowserManagerInterface
from backend.desktop.browser_paths import resolve_browser_candidates

CDP_PORT = 9222
CDP_HOST = "127.0.0.1"
CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe"
CHROME_USER_DATA_DIR = Path.cwd() / ".chrome-profile"


def build_chrome_launch_args(user_data_dir: str | Path | None = None) -> list[str]:
    profile_dir = str(user_data_dir) if user_data_dir else str(CHROME_USER_DATA_DIR)
    return [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-background-mode",
    ]


class PlaywrightBrowserManager(BrowserManagerInterface):
    """Manages Playwright browser lifecycle.

    Supports two modes:
      1. CDP mode (default when no browser_ws_endpoint set):
         connects to a real Chrome via `connect_over_cdp`
      2. Launched mode: uses browser_ws_endpoint or launches headless Chromium.
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._chrome_process: subprocess.Popen | None = None
        self._owns_chrome_process = False
        self._is_cdp = False
        self._reconnect_lock = asyncio.Lock()
        self._selected_browser_kind: str | None = None
        self._launch_attempts: list[dict[str, str]] = []
        self._avoid_browser_kind_once: str | None = None
        self._headless = True

    @property
    def selected_browser_kind(self) -> str | None:
        return self._selected_browser_kind

    @property
    def launch_attempts(self) -> list[dict[str, str]]:
        return list(self._launch_attempts)

    async def start(self) -> None:
        self._playwright = await async_playwright().start()

        if os.environ.get("RUNTIME_MODE") == "desktop":
            self._launch_attempts = []
            last_error: Exception | None = None
            try:
                candidates = resolve_browser_candidates()
            except Exception:  # noqa: BLE001 - release Playwright before propagating
                await self._playwright.stop()
                self._playwright = None
                raise
            avoided = self._avoid_browser_kind_once
            self._avoid_browser_kind_once = None
            if avoided:
                candidates = sorted(
                    candidates,
                    key=lambda candidate: candidate.kind == avoided,
                )
            for candidate in candidates:
                browser = None
                try:
                    browser = await self._playwright.chromium.launch(
                        executable_path=str(candidate.executable),
                        headless=self._headless,
                        args=["--no-sandbox"],
                    )
                    context = await browser.new_context()
                except Exception as error:  # noqa: BLE001 - try the next installed browser
                    last_error = error
                    self._launch_attempts.append(
                        {"browser": candidate.kind, "status": "failed"}
                    )
                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception as close_error:  # noqa: BLE001 - launch error wins
                            logger.warning(
                                "Browser cleanup failed after launch error: {}",
                                type(close_error).__name__,
                            )
                    continue
                self._browser = browser
                self._context = context
                self._selected_browser_kind = candidate.kind
                self._launch_attempts.append(
                    {"browser": candidate.kind, "status": "passed"}
                )
                break
            if self._browser is None:
                await self._playwright.stop()
                self._playwright = None
                raise BrowserError("DESKTOP_BROWSER_START_FAILED") from last_error
        elif settings.browser_ws_endpoint:
            self._browser = await self._playwright.chromium.connect(
                ws_endpoint=settings.browser_ws_endpoint,
            )
            self._context = await self._browser.new_context()
        else:
            await self._start_cdp()

    async def _start_cdp(self) -> None:
        """Launch local Chrome with CDP if not already running, then connect."""
        if not await self._check_cdp():
            if not Path(CHROME_PATH).exists():
                raise BrowserError(f"Chrome executable not found: {CHROME_PATH}")
            CHROME_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._chrome_process = subprocess.Popen(build_chrome_launch_args(), shell=False)
            self._owns_chrome_process = True
        elif self._chrome_process is None:
            self._owns_chrome_process = False

        self._browser = await self._connect_over_cdp_with_retry()
        self._is_cdp = True

        if self._browser.contexts:
            self._context = self._browser.contexts[0]
        else:
            self._context = await self._browser.new_context()

    async def _check_cdp(self) -> bool:
        import urllib.request
        try:
            resp = urllib.request.urlopen(
                f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=2
            )
            return resp.status == 200
        except Exception:
            return False

    async def _connect_over_cdp_with_retry(self, timeout_seconds: int = 15) -> Browser:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                return await self._playwright.chromium.connect_over_cdp(
                    f"http://{CDP_HOST}:{CDP_PORT}",
                )
            except Exception as e:
                last_error = e
            await asyncio.sleep(0.5)
        raise BrowserError(
            f"Failed to connect to Chrome CDP on port {CDP_PORT} "
            f"within {timeout_seconds} seconds: {last_error}"
        ) from last_error

    async def stop(self, *, raise_errors: bool = True) -> None:
        errors: list[Exception] = []
        if self._context and not self._is_cdp:
            try:
                await self._context.close()
            except Exception as e:
                errors.append(e)
        if self._browser and not self._is_cdp:
            try:
                await self._browser.close()
            except Exception as e:
                errors.append(e)
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                errors.append(e)

        if self._chrome_process and self._owns_chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._chrome_process.kill()
                self._chrome_process.wait(timeout=5)
            except Exception as e:
                errors.append(e)

        self._context = None
        self._browser = None
        self._playwright = None
        self._chrome_process = None
        self._owns_chrome_process = False
        self._selected_browser_kind = None

        if errors and raise_errors:
            raise BrowserError(f"Failed to stop browser: {errors[0]}") from errors[0]

    async def restart(self) -> None:
        self._avoid_browser_kind_once = self._selected_browser_kind
        await self.stop(raise_errors=False)
        await self.start()

    async def restart_visible(self) -> None:
        self._headless = False
        await self.stop(raise_errors=False)
        await self.start()

    async def new_page(self) -> Page:
        if not self._context:
            raise BrowserError("Browser context not initialized. Call start() first.")
        try:
            return await self._context.new_page()
        except Exception as e:
            if not self._is_cdp:
                if _is_target_closed(e):
                    raise BrowserTargetClosedError() from e
                raise BrowserError(f"Failed to create page: {e}") from e

            async with self._reconnect_lock:
                try:
                    if self._context:
                        return await self._context.new_page()
                except Exception:
                    await self._start_cdp()

                if not self._context:
                    raise BrowserError("Browser context not initialized after reconnect")
                return await self._context.new_page()


def _is_target_closed(error: BaseException) -> bool:
    name = type(error).__name__.lower()
    message = str(error).lower()
    return (
        "targetclosed" in name
        or "target page, context or browser has been closed" in message
    )


__all__ = ["PlaywrightBrowserManager", "build_chrome_launch_args"]
