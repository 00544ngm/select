from __future__ import annotations

import os

import uvicorn

from backend.config import database_connection_url, get_backend_settings
from backend.desktop.migrations import upgrade_database


def build_uvicorn_args(port: int) -> dict[str, object]:
    return {
        "app": "backend.main:app",
        "host": "127.0.0.1",
        "port": port,
        "log_config": None,
    }


def main() -> None:
    settings = get_backend_settings()
    if settings.runtime_mode != "desktop":
        raise SystemExit("桌面 API 必须使用 desktop 运行模式")
    port = int(os.environ["DESKTOP_API_PORT"])
    upgrade_database(database_connection_url(settings))
    uvicorn.run(**build_uvicorn_args(port))


if __name__ == "__main__":
    main()


__all__ = ["build_uvicorn_args", "main"]
