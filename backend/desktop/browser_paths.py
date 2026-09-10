from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class PackagedBrowserMissingError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserCandidate:
    kind: str
    executable: Path


def _default_edge_paths() -> list[Path]:
    candidates: list[Path] = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            )
    return candidates


def resolve_browser_executable(resource_dir: Path | None = None) -> Path:
    explicit = os.environ.get("DESKTOP_BROWSER_EXECUTABLE")
    if explicit:
        executable = Path(explicit).resolve()
    else:
        root = resource_dir or Path(os.environ.get("DESKTOP_RESOURCE_DIR", ""))
        executable = (root / "browser" / "chrome-win64" / "chrome.exe").resolve()
    if not executable.is_file():
        raise PackagedBrowserMissingError("PACKAGED_BROWSER_MISSING")
    return executable


def resolve_browser_candidates(
    resource_dir: Path | None = None,
    *,
    edge_paths: list[Path] | None = None,
) -> list[BrowserCandidate]:
    candidates: list[BrowserCandidate] = []
    seen: set[Path] = set()
    for path in edge_paths if edge_paths is not None else _default_edge_paths():
        executable = path.resolve()
        if executable.is_file() and executable not in seen:
            candidates.append(BrowserCandidate("edge", executable))
            seen.add(executable)
    try:
        bundled = resolve_browser_executable(resource_dir)
    except PackagedBrowserMissingError:
        bundled = None
    if bundled is not None and bundled not in seen:
        candidates.append(BrowserCandidate("bundled_chromium", bundled))
    if not candidates:
        raise PackagedBrowserMissingError("DESKTOP_BROWSER_MISSING")
    return candidates


__all__ = [
    "BrowserCandidate",
    "PackagedBrowserMissingError",
    "resolve_browser_candidates",
    "resolve_browser_executable",
]
