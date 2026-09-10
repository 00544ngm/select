from backend.desktop.api_entry import build_uvicorn_args
from backend.main import app


def test_api_entry_binds_loopback_only() -> None:
    args = build_uvicorn_args(43127)

    assert args["host"] == "127.0.0.1"
    assert args["port"] == 43127
    assert args["app"] == "backend.main:app"


def test_packaged_api_reports_release_version() -> None:
    assert app.version == "0.1.15"
