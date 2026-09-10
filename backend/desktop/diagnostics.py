from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from backend.desktop.paths import DesktopPaths

BrowserProbe = Callable[[], Awaitable[dict[str, Any] | None]]


def _check(status: str, code: str, summary: str) -> dict[str, str]:
    return {"status": status, "code": code, "summary": summary}


def _probe_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f".diagnostic-{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


async def _probe_packaged_browser() -> dict[str, Any]:
    from app.infrastructure.browser import PlaywrightBrowserManager

    browser = PlaywrightBrowserManager()
    try:
        await browser.start()
        page = await browser.new_page()
        await page.goto("about:blank")
        await page.close()
        return {
            "selected": browser.selected_browser_kind,
            "attempts": browser.launch_attempts,
        }
    finally:
        await browser.stop(raise_errors=False)


async def run_desktop_diagnostics(
    *,
    paths: DesktopPaths | None = None,
    browser_probe: BrowserProbe | None = None,
) -> dict[str, Any]:
    active_paths = paths or DesktopPaths.for_current_user()
    checks: dict[str, dict[str, str]] = {}
    try:
        for path in (
            active_paths.data_dir / "data",
            active_paths.log_dir,
            active_paths.artifact_dir,
            active_paths.temp_dir,
        ):
            _probe_writable(path)
        checks["runtime_paths"] = _check(
            "passed", "DESKTOP_PATHS_OK", "数据、日志、报告和临时目录可正常写入"
        )
    except OSError:
        checks["runtime_paths"] = _check(
            "failed", "DESKTOP_PATH_NOT_WRITABLE", "桌面运行目录无法写入"
        )

    try:
        browser_result = await (browser_probe or _probe_packaged_browser)()
        checks["browser"] = _check(
            "passed", "DESKTOP_BROWSER_OK", "浏览器组件可以启动并创建页面"
        )
        if browser_result:
            checks["browser"].update(browser_result)
    except Exception:
        checks["browser"] = _check(
            "failed",
            "DESKTOP_BROWSER_START_FAILED",
            "浏览器组件启动失败或启动后被外部终止",
        )

    checks["windows_security"] = _check(
        "manual_check",
        "WINDOWS_SECURITY_MANUAL_CHECK",
        "如浏览器检查失败，请打开 Windows 安全中心查看保护历史记录",
    )
    return {"status": "passed" if all(c["status"] != "failed" for c in checks.values()) else "failed", "checks": checks}


__all__ = ["run_desktop_diagnostics"]
