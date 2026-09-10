from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from backend.desktop.migration.exporter import TABLE_ORDER
from backend.desktop.migration.manifest import MigrationManifest


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()
    candidate_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.ok and self.errors:
            raise ValueError("successful validation cannot contain errors")
        if self.ok and not self.candidate_fingerprint:
            raise ValueError("successful validation requires a candidate fingerprint")
        if not self.ok and not self.errors:
            object.__setattr__(self, "errors", ("validation_failed",))


class MigrationValidationError(RuntimeError):
    def __init__(self, errors: tuple[str, ...]) -> None:
        super().__init__("migration validation failed")
        self.errors = errors


def _read_only_uri(database_file: Path) -> str:
    return f"file:{database_file.resolve().as_posix()}?mode=ro"


def candidate_fingerprint(candidate: Path) -> str:
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = candidate.stat()
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{digest.hexdigest()}"


def validate_candidate(
    candidate: Path,
    manifest: MigrationManifest,
) -> ValidationResult:
    errors: list[str] = []
    if manifest.source_counts != manifest.target_counts:
        errors.append("manifest_count_mismatch")
    try:
        resolved_candidate = candidate.resolve()
        resolved_manifest_candidate = manifest.candidate_file.resolve()
    except OSError:
        return ValidationResult(ok=False, errors=("candidate_unreadable",))
    if resolved_candidate != resolved_manifest_candidate:
        return ValidationResult(ok=False, errors=("candidate_path_mismatch",))
    if not candidate.is_file():
        return ValidationResult(ok=False, errors=("candidate_missing",))

    fingerprint: str | None = None
    try:
        initial_fingerprint = candidate_fingerprint(candidate)
        with closing(
            sqlite3.connect(_read_only_uri(candidate), uri=True)
        ) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            if integrity != ("ok",):
                errors.append("sqlite_integrity_failed")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                errors.append("sqlite_foreign_key_failed")

            for table_name in TABLE_ORDER:
                count = int(
                    connection.execute(
                        f'SELECT count(*) FROM "{table_name}"'
                    ).fetchone()[0]
                )
                if count != manifest.target_counts.get(table_name):
                    errors.append(f"count_mismatch:{table_name}")

            version = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            if version != (manifest.schema_version,):
                errors.append("schema_version_mismatch")

            for (payload,) in connection.execute(
                "SELECT result_payload FROM analysis_jobs "
                "WHERE result_payload IS NOT NULL"
            ):
                if isinstance(payload, str):
                    json.loads(payload)
        fingerprint = candidate_fingerprint(candidate)
        if initial_fingerprint != fingerprint:
            errors.append("candidate_changed_during_validation")
            fingerprint = None
    except (json.JSONDecodeError, OSError, sqlite3.DatabaseError, TypeError, ValueError):
        errors.append("candidate_unreadable")

    return ValidationResult(
        ok=not errors,
        errors=tuple(dict.fromkeys(errors)),
        candidate_fingerprint=fingerprint if not errors else None,
    )


__all__ = [
    "MigrationValidationError",
    "ValidationResult",
    "candidate_fingerprint",
    "validate_candidate",
]
