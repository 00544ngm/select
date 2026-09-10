from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesktopPaths:
    data_dir: Path

    @classmethod
    def for_current_user(cls) -> DesktopPaths:
        return cls(data_dir=Path(os.environ["LOCALAPPDATA"]) / "组合选品控制台")

    @property
    def database_file(self) -> Path:
        return self.data_dir / "data" / "bundling.db"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def worker_heartbeat_file(self) -> Path:
        return self.data_dir / "runtime" / "worker-heartbeat.json"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def artifact_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temp"


__all__ = ["DesktopPaths"]
