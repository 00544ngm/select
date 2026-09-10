from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESTART_SCRIPT = PROJECT_ROOT / "scripts" / "restart-and-verify.ps1"
LAUNCHER_SCRIPT = PROJECT_ROOT / "启动.ps1"


def _script_text(path: Path) -> str:
    assert path.is_file(), f"missing script: {path}"
    return path.read_text(encoding="utf-8")


def test_restart_script_scopes_processes_to_current_project() -> None:
    script = _script_text(RESTART_SCRIPT)

    assert "Get-CimInstance Win32_Process" in script
    assert "$ProjectRoot = (Resolve-Path" in script
    assert "IndexOf($ProjectRoot" in script
    assert "[regex]::Escape($ProjectRoot" in script
    assert "$ProjectRootPattern" in script
    assert "[System.StringComparison]::OrdinalIgnoreCase" in script
    assert "uvicorn backend.main:app" in script
    assert "arq backend.workers.settings.WorkerSettings" in script
    assert "next dev" in script
    assert "next\\dist\\bin\\next" in script
    assert "ParentProcessId" in script
    assert "[array]::Reverse" in script
    assert "$_.ProcessId -ne $PID" in script
    assert "Get-Process -Name python" not in script
    assert "Stop-Process -Id $Process.ProcessId" in script
    assert "-Force" in script


def test_restart_script_guards_cache_and_secrets() -> None:
    script = _script_text(RESTART_SCRIPT)

    assert "Resolve-Path" in script
    assert "[System.IO.Path]::GetRelativePath" in script
    assert "$ResolvedCache.Substring" in script
    assert "MakeRelativeUri" not in script
    assert "Get-Item -LiteralPath $CachePath" in script
    assert "ReparsePoint" in script
    assert "Remove-Item -Recurse -Force -LiteralPath" in script
    assert "Get-Content" not in script
    assert ".env" not in script
    assert "-WindowStyle Hidden" in script
    assert "-RedirectStandardOutput" in script
    assert "-RedirectStandardError" in script


def test_restart_script_supports_check_only_and_runtime_verification() -> None:
    script = _script_text(RESTART_SCRIPT)

    assert "[switch]$CheckOnly" in script
    assert "/api/v1/health/live" in script
    assert "/api/v1/health/ready" in script
    assert "contract_match" in script
    assert "api_model_version" in script
    assert "worker_model_version" in script
    assert "combination_model_v2.1" in script
    assert "/api/v1/settings/providers" in script
    assert "@($Providers).Count -lt 1" in script
    assert "/settings/api" in script
    assert "/_next/static/" in script
    assert "$AssetMatches.Count -eq 0" in script
    assert "exit 1" in script


def test_launcher_delegates_to_project_restart_script() -> None:
    launcher = _script_text(LAUNCHER_SCRIPT)

    assert "scripts\\restart-and-verify.ps1" in launcher
    assert "& $RestartScript" in launcher
    assert "powershell" not in launcher.lower()
    assert "Get-Process -Name" not in launcher
    assert "Get-Content" not in launcher
    assert "Start-Process" not in launcher
