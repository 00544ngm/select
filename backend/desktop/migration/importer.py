from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import create_database_engine
from backend.db.session import create_session_factory
from backend.desktop.migration.exporter import (
    TABLE_ORDER,
    TABLES,
    install_source_read_only_guard,
    read_table,
)
from backend.desktop.migration.manifest import MigrationManifest, build_manifest
from backend.desktop.migrations import upgrade_database_async


class MigrationCleanupError(RuntimeError):
    """Migration completed but owned resources could not be cleaned up."""


async def _copy_table(
    source_session: AsyncSession,
    target_session: AsyncSession,
    table_name: str,
) -> int:
    rows = await read_table(source_session, table_name)
    if rows:
        await target_session.execute(insert(TABLES[table_name]), rows)
    return len(rows)


def _migration_paths(target_file: Path) -> tuple[Path, Path]:
    candidate = target_file.with_suffix(".candidate.db")
    return candidate, candidate.with_suffix(".failed.db")


def _claim_candidate(candidate: Path) -> None:
    descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)


def _diagnostic_note(component: str, error: BaseException) -> str:
    errno = getattr(error, "errno", None)
    suffix = f" errno={errno}" if errno is not None else ""
    return f"{component}: {type(error).__name__}{suffix}"


async def migrate_read_only(source_url: str, target_file: Path) -> MigrationManifest:
    candidate, failed = _migration_paths(target_file)
    if failed.exists():
        raise FileExistsError(f"failed migration candidate already exists: {failed}")
    _claim_candidate(candidate)
    owns_candidate = True

    candidate_url = f"sqlite+aiosqlite:///{candidate.resolve().as_posix()}"
    source_engine = None
    target_engine = None
    manifest = None
    migration_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []
    rename_error: OSError | None = None
    source_counts: dict[str, int] = {}
    try:
        await upgrade_database_async(candidate_url, "head")
        source_engine = create_database_engine(source_url)
        target_engine = create_database_engine(candidate_url)
        source_factory = create_session_factory(source_engine)
        target_factory = create_session_factory(target_engine)
        async with source_factory() as source_session, source_session.begin():
            connection = await source_session.connection()
            await connection.run_sync(install_source_read_only_guard)
            async with target_factory() as target_session, target_session.begin():
                for table_name in TABLE_ORDER:
                    source_counts[table_name] = await _copy_table(
                        source_session, target_session, table_name
                    )
        manifest = await build_manifest(source_counts, target_engine, candidate)
    except BaseException as exc:  # noqa: BLE001 - cancellation must still clean up
        migration_error = exc
    finally:
        engines = [engine for engine in (source_engine, target_engine) if engine]
        if engines:
            results = await asyncio.gather(
                *(engine.dispose() for engine in engines),
                return_exceptions=True,
            )
            cleanup_errors = [
                result for result in results if isinstance(result, BaseException)
            ]
        if (
            (migration_error is not None or cleanup_errors)
            and owns_candidate
            and candidate.exists()
            and not failed.exists()
        ):
            try:
                candidate.replace(failed)
            except OSError as exc:
                rename_error = exc

    if migration_error is not None:
        for error in cleanup_errors:
            migration_error.add_note(_diagnostic_note("engine cleanup", error))
        if rename_error is not None:
            migration_error.add_note(_diagnostic_note("failed rename", rename_error))
        raise migration_error.with_traceback(migration_error.__traceback__)
    if cleanup_errors:
        error = MigrationCleanupError("migration cleanup failed")
        for cleanup_error in cleanup_errors:
            error.add_note(_diagnostic_note("engine cleanup", cleanup_error))
        if rename_error is not None:
            error.add_note(_diagnostic_note("failed rename", rename_error))
        raise error from cleanup_errors[0]
    if manifest is None:
        raise RuntimeError("migration completed without a manifest")
    return manifest


__all__ = ["MigrationCleanupError", "migrate_read_only"]
