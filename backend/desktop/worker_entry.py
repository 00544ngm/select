from __future__ import annotations

from backend.config import get_backend_settings
from backend.workers.local_worker import main as run_local_worker


def main() -> None:
    if get_backend_settings().runtime_mode != "desktop":
        raise SystemExit("桌面 Worker 必须使用 desktop 运行模式")
    run_local_worker()


if __name__ == "__main__":
    main()


__all__ = ["main"]
