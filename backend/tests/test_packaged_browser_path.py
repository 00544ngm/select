from pathlib import Path

import pytest

from backend.desktop.browser_paths import (
    PackagedBrowserMissingError,
    resolve_browser_candidates,
    resolve_browser_executable,
)


def test_packaged_browser_path_is_inside_resources(tmp_path: Path) -> None:
    executable = tmp_path / "browser" / "chrome-win64" / "chrome.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()

    resolved = resolve_browser_executable(tmp_path)

    assert resolved.is_relative_to(tmp_path)
    assert resolved.name.lower() == "chrome.exe"


def test_missing_packaged_browser_has_stable_error(tmp_path: Path) -> None:
    with pytest.raises(PackagedBrowserMissingError, match="PACKAGED_BROWSER_MISSING"):
        resolve_browser_executable(tmp_path)


def test_desktop_browser_candidates_prefer_edge_then_bundled(tmp_path: Path) -> None:
    edge = tmp_path / "edge" / "msedge.exe"
    bundled = tmp_path / "browser" / "chrome-win64" / "chrome.exe"
    edge.parent.mkdir(parents=True)
    bundled.parent.mkdir(parents=True)
    edge.touch()
    bundled.touch()

    candidates = resolve_browser_candidates(tmp_path, edge_paths=[edge])

    assert [candidate.kind for candidate in candidates] == [
        "edge",
        "bundled_chromium",
    ]
    assert candidates[0].executable == edge.resolve()


def test_desktop_browser_candidates_keep_bundled_when_edge_missing(tmp_path: Path) -> None:
    bundled = tmp_path / "browser" / "chrome-win64" / "chrome.exe"
    bundled.parent.mkdir(parents=True)
    bundled.touch()

    candidates = resolve_browser_candidates(
        tmp_path,
        edge_paths=[tmp_path / "missing" / "msedge.exe"],
    )

    assert [candidate.kind for candidate in candidates] == ["bundled_chromium"]
