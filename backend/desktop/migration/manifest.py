from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.desktop.migration.exporter import TABLE_ORDER, TABLES


@dataclass(frozen=True)
class MigrationManifest:
    source_counts: dict[str, int]
    target_counts: dict[str, int]
    candidate_file: Path
    schema_version: str
    created_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "source_counts": self.source_counts,
            "target_counts": self.target_counts,
            "candidate_file": self.candidate_file.name,
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
        }


async def _counts(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as connection:
        return {
            name: int(
                (await connection.execute(select(func.count()).select_from(TABLES[name]))).scalar_one()
            )
            for name in TABLE_ORDER
        }


async def build_manifest(
    source_counts: dict[str, int],
    target_engine: AsyncEngine,
    candidate_file: Path,
) -> MigrationManifest:
    target_counts = await _counts(target_engine)
    if source_counts != target_counts:
        raise ValueError(
            f"migration count mismatch: source={source_counts}, target={target_counts}"
        )
    async with target_engine.connect() as connection:
        version = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    return MigrationManifest(
        source_counts=source_counts,
        target_counts=target_counts,
        candidate_file=candidate_file,
        schema_version=str(version),
        created_at=datetime.now(timezone.utc),
    )


__all__ = ["MigrationManifest", "build_manifest"]
