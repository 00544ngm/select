from __future__ import annotations

import os
import shutil
import sqlite3
import threading
from collections import namedtuple
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.desktop.backup import (
    DesktopMigrationIOError,
    InsufficientDiskSpaceError,
    LiveDatabaseBusyError,
    MigrationPathError,
    PromotionInProgressError,
    database_write_guard,
    promote_candidate,
)
from backend.desktop.migration.exporter import TABLE_ORDER
from backend.desktop.migration.manifest import MigrationManifest
from backend.desktop.migration.validator import (
    MigrationValidationError,
    validate_candidate,
)
from backend.desktop.migrations import upgrade_database


def create_database(path: Path, *, user_version: int = 0) -> None:
    upgrade_database(f"sqlite+aiosqlite:///{path.as_posix()}")
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(f"PRAGMA user_version={user_version}")
        connection.commit()


def candidate_manifest(
    candidate: Path,
    *,
    source_counts: dict[str, int] | None = None,
    target_counts: dict[str, int] | None = None,
) -> MigrationManifest:
    counts = {table_name: 0 for table_name in TABLE_ORDER}
    with closing(sqlite3.connect(candidate)) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    return MigrationManifest(
        source_counts=source_counts or counts,
        target_counts=target_counts or counts,
        candidate_file=candidate,
        schema_version=version,
        created_at=datetime.now(timezone.utc),
    )


def prepare_databases(tmp_path: Path) -> tuple[Path, Path, MigrationManifest, Path]:
    live = tmp_path / "bundling.db"
    candidate = tmp_path / "bundling.candidate.db"
    create_database(live, user_version=1)
    create_database(candidate, user_version=2)
    return live, candidate, candidate_manifest(candidate), tmp_path / "backups"


def user_version(path: Path) -> int:
    with closing(
        sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    ) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def test_validator_accepts_intact_migrated_candidate(tmp_path) -> None:
    candidate = tmp_path / "bundling.candidate.db"
    create_database(candidate)

    result = validate_candidate(candidate, candidate_manifest(candidate))

    assert result.ok
    assert not result.errors
    assert result.candidate_fingerprint


def test_promote_runs_real_validation_and_rejects_wrong_manifest(tmp_path) -> None:
    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    bad_counts = dict(manifest.source_counts)
    bad_counts["analysis_jobs"] = 1
    bad_manifest = MigrationManifest(
        source_counts=bad_counts,
        target_counts=manifest.target_counts,
        candidate_file=candidate,
        schema_version=manifest.schema_version,
        created_at=manifest.created_at,
    )
    before_live = live.read_bytes()
    before_candidate = candidate.read_bytes()

    with pytest.raises(MigrationValidationError, match="validation failed"):
        promote_candidate(candidate, live, backup_dir, bad_manifest)

    assert live.read_bytes() == before_live
    assert candidate.read_bytes() == before_candidate
    assert not backup_dir.exists()


def test_candidate_replaced_after_validation_is_not_promoted(tmp_path, monkeypatch) -> None:
    from backend.desktop import backup

    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    replacement = tmp_path / "replacement.db"
    create_database(replacement, user_version=99)
    real_validate = backup.validate_candidate

    def validate_then_swap(candidate_path, candidate_manifest_value):
        result = real_validate(candidate_path, candidate_manifest_value)
        os.replace(replacement, candidate_path)
        return result

    monkeypatch.setattr(backup, "validate_candidate", validate_then_swap)
    with pytest.raises(MigrationValidationError) as raised:
        promote_candidate(candidate, live, backup_dir, manifest)

    assert raised.value.errors == ("candidate changed after validation",)
    assert user_version(live) == 1
    assert user_version(candidate) == 99
    assert not backup_dir.exists()


@pytest.mark.parametrize(
    "candidate_factory",
    [
        lambda root: root / "unexpected.db",
        lambda root: root / "other" / "bundling.candidate.db",
    ],
)
def test_candidate_path_must_match_owned_live_candidate_contract(
    tmp_path, candidate_factory
) -> None:
    live = tmp_path / "bundling.db"
    candidate = candidate_factory(tmp_path)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    create_database(live)
    create_database(candidate)

    with pytest.raises(MigrationPathError, match="candidate path"):
        promote_candidate(
            candidate,
            live,
            tmp_path / "backups",
            candidate_manifest(candidate),
        )

    assert user_version(live) == 0
    assert candidate.exists()


def test_successful_promotion_keeps_non_overwritten_sqlite_backup(tmp_path) -> None:
    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)

    result = promote_candidate(candidate, live, backup_dir, manifest)

    assert user_version(live) == 2
    assert not candidate.exists()
    assert result.backup_file is not None
    assert user_version(result.backup_file) == 1

    replacement = live.with_suffix(".candidate.db")
    create_database(replacement, user_version=3)
    second = promote_candidate(
        replacement,
        live,
        backup_dir,
        candidate_manifest(replacement),
    )
    assert second.backup_file is not None
    assert second.backup_file != result.backup_file
    assert user_version(result.backup_file) == 1
    assert user_version(second.backup_file) == 2


def create_uncheckpointed_wal_snapshot(live: Path, source: Path) -> None:
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE wal_probe(value TEXT NOT NULL)")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("INSERT INTO wal_probe VALUES ('committed-in-wal')")
        connection.commit()
        shutil.copyfile(source, live)
        shutil.copyfile(source.with_name(f"{source.name}-wal"), live.with_name(f"{live.name}-wal"))
        shutil.copyfile(source.with_name(f"{source.name}-shm"), live.with_name(f"{live.name}-shm"))
    finally:
        connection.close()


def test_sqlite_backup_includes_committed_uncheckpointed_wal_data(tmp_path) -> None:
    live = tmp_path / "bundling.db"
    source = tmp_path / "wal-source.db"
    create_uncheckpointed_wal_snapshot(live, source)
    candidate = tmp_path / "bundling.candidate.db"
    create_database(candidate, user_version=2)

    result = promote_candidate(
        candidate,
        live,
        tmp_path / "backups",
        candidate_manifest(candidate),
    )

    assert result.backup_file is not None
    with closing(sqlite3.connect(result.backup_file)) as backup_connection:
        assert backup_connection.execute("SELECT value FROM wal_probe").fetchone() == (
            "committed-in-wal",
        )
    assert not live.with_name(f"{live.name}-wal").exists()
    assert not live.with_name(f"{live.name}-shm").exists()


def test_active_live_writer_blocks_backup_and_promotion(tmp_path) -> None:
    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    writer = sqlite3.connect(live)
    writer.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(LiveDatabaseBusyError, match="writes must be stopped"):
            promote_candidate(candidate, live, backup_dir, manifest)
    finally:
        writer.rollback()
        writer.close()

    assert user_version(live) == 1
    assert user_version(candidate) == 2


def test_writer_cannot_enter_after_backup_before_replace(tmp_path, monkeypatch) -> None:
    from backend.desktop import backup

    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    backup_finished = threading.Event()
    allow_promotion = threading.Event()
    real_backup = backup._sqlite_backup
    outcome: list[object] = []

    def pause_after_backup(*args, **kwargs):
        real_backup(*args, **kwargs)
        backup_finished.set()
        assert allow_promotion.wait(timeout=10)

    def run_promotion() -> None:
        try:
            outcome.append(promote_candidate(candidate, live, backup_dir, manifest))
        except Exception as error:  # noqa: BLE001 - forward thread failures
            outcome.append(error)

    monkeypatch.setattr(backup, "_sqlite_backup", pause_after_backup)
    thread = threading.Thread(target=run_promotion)
    thread.start()
    assert backup_finished.wait(timeout=10)
    try:
        with (
            pytest.raises(PromotionInProgressError),
            database_write_guard(live, blocking=False),
        ):
            pytest.fail("writer entered while promotion was paused")
    finally:
        allow_promotion.set()
        thread.join(timeout=10)

    assert len(outcome) == 1
    assert not isinstance(outcome[0], BaseException)
    assert user_version(live) == 2


def test_candidate_wal_is_checkpointed_before_validation_and_promoted(tmp_path) -> None:
    live = tmp_path / "bundling.db"
    create_database(live, user_version=1)
    candidate = tmp_path / "bundling.candidate.db"
    source = tmp_path / "candidate-source.db"
    create_database(source, user_version=2)
    manifest = candidate_manifest(source)
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("PRAGMA user_version=77")
        connection.commit()
        shutil.copyfile(source, candidate)
        for suffix in ("-wal", "-shm"):
            shutil.copyfile(
                source.with_name(f"{source.name}{suffix}"),
                candidate.with_name(f"{candidate.name}{suffix}"),
            )
    finally:
        connection.close()
    manifest = MigrationManifest(
        source_counts=manifest.source_counts,
        target_counts=manifest.target_counts,
        candidate_file=candidate,
        schema_version=manifest.schema_version,
        created_at=manifest.created_at,
    )

    promote_candidate(candidate, live, tmp_path / "backups", manifest)

    assert user_version(live) == 77
    assert not live.with_name(f"{live.name}-wal").exists()
    assert not live.with_name(f"{live.name}-shm").exists()


def test_candidate_sidecar_created_after_validation_blocks_promotion(
    tmp_path, monkeypatch
) -> None:
    from backend.desktop import backup

    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    real_validate = backup.validate_candidate

    def validate_then_create_wal(*args, **kwargs):
        result = real_validate(*args, **kwargs)
        candidate.with_name(f"{candidate.name}-wal").write_bytes(b"late wal")
        return result

    monkeypatch.setattr(backup, "validate_candidate", validate_then_create_wal)
    with pytest.raises(MigrationValidationError) as raised:
        promote_candidate(candidate, live, backup_dir, manifest)

    assert "candidate_sidecar_changed" in raised.value.errors
    assert user_version(live) == 1
    assert candidate.exists()
    assert not backup_dir.exists()


def test_insufficient_space_preserves_live_candidate_and_existing_backups(
    tmp_path, monkeypatch
) -> None:
    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    backup_dir.mkdir()
    existing = backup_dir / "existing.db"
    existing.write_bytes(b"existing backup")
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage(100, 99, 1))

    with pytest.raises(InsufficientDiskSpaceError, match="insufficient disk space"):
        promote_candidate(candidate, live, backup_dir, manifest)

    assert user_version(live) == 1
    assert user_version(candidate) == 2
    assert existing.read_bytes() == b"existing backup"
    assert list(backup_dir.iterdir()) == [existing]


def test_replace_oserror_is_sanitized_and_preserves_recoverable_backup(
    tmp_path, monkeypatch
) -> None:
    from backend.desktop import backup

    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    private_path = str(tmp_path / "secret-user" / "bundling.db")

    def fail_replace(*_args, **_kwargs):
        raise PermissionError(13, "secret-message", private_path)

    monkeypatch.setattr(backup.os, "replace", fail_replace)
    with pytest.raises(DesktopMigrationIOError) as raised:
        promote_candidate(candidate, live, backup_dir, manifest)

    diagnostic = str(raised.value) + " " + " ".join(raised.value.__notes__)
    assert raised.value.stage == "replace_live"
    assert "PermissionError" in diagnostic
    assert "errno=13" in diagnostic
    assert "secret" not in diagnostic
    assert private_path not in diagnostic
    assert user_version(live) == 1
    assert user_version(candidate) == 2
    backups = list(backup_dir.glob("*.db"))
    assert len(backups) == 1
    assert user_version(backups[0]) == 1


@pytest.mark.parametrize(
    "failing_stage",
    ["mkdir", "stat", "disk_usage", "sqlite_backup", "fsync", "sidecar"],
)
def test_other_filesystem_oserrors_are_sanitized(
    tmp_path, monkeypatch, failing_stage
) -> None:
    from backend.desktop import backup

    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    private_path = str(tmp_path / "secret-user" / "file.db")

    def failure(*_args, **_kwargs):
        raise OSError(5, "secret-message", private_path)

    if failing_stage == "mkdir":
        monkeypatch.setattr(backup, "_make_backup_directory", failure)
    elif failing_stage == "stat":
        monkeypatch.setattr(backup, "_required_backup_space", failure)
    elif failing_stage == "disk_usage":
        monkeypatch.setattr(backup, "_available_disk_space", failure)
    elif failing_stage == "sqlite_backup":
        monkeypatch.setattr(backup, "_sqlite_backup", failure)
    elif failing_stage == "fsync":
        monkeypatch.setattr(backup, "_fsync_file", failure)
    else:
        monkeypatch.setattr(backup, "_remove_sidecar", failure)

    with pytest.raises(DesktopMigrationIOError) as raised:
        promote_candidate(candidate, live, backup_dir, manifest)

    diagnostic = str(raised.value) + " " + " ".join(raised.value.__notes__)
    assert "OSError" in diagnostic
    assert "errno=5" in diagnostic
    assert "secret" not in diagnostic
    assert private_path not in diagnostic
    assert user_version(live) == 1
    assert user_version(candidate) == 2


@pytest.mark.parametrize("operation", ["resolve", "is_file", "connection_cleanup"])
def test_path_and_connection_cleanup_errors_are_sanitized(
    tmp_path, monkeypatch, operation
) -> None:
    from backend.desktop import backup

    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    private_path = str(tmp_path / "secret-user" / "file.db")

    def failure(*_args, **_kwargs):
        raise OSError(5, "secret-message", private_path)

    monkeypatch.setattr(
        backup,
        {
            "resolve": "_resolve_path",
            "is_file": "_is_file",
            "connection_cleanup": "_close_connection",
        }[operation],
        failure,
    )
    with pytest.raises(DesktopMigrationIOError) as raised:
        promote_candidate(candidate, live, backup_dir, manifest)

    diagnostic = str(raised.value) + " " + " ".join(raised.value.__notes__)
    assert "OSError" in diagnostic
    assert "errno=5" in diagnostic
    assert "secret" not in diagnostic
    assert private_path not in diagnostic
    assert live.exists()
    assert candidate.exists()


def test_promotion_lock_cleanup_error_does_not_mask_validation_error(
    tmp_path, monkeypatch
) -> None:
    from backend.desktop import backup

    live, candidate, manifest, backup_dir = prepare_databases(tmp_path)
    bad_counts = dict(manifest.source_counts)
    bad_counts["analysis_jobs"] = 1
    bad_manifest = MigrationManifest(
        source_counts=bad_counts,
        target_counts=manifest.target_counts,
        candidate_file=candidate,
        schema_version=manifest.schema_version,
        created_at=manifest.created_at,
    )
    private_path = str(tmp_path / "secret-user" / "promotion.lock")

    def fail_release(*_args, **_kwargs):
        raise OSError(5, "secret-message", private_path)

    monkeypatch.setattr(backup, "_release_file_lock", fail_release)
    with pytest.raises(MigrationValidationError) as raised:
        promote_candidate(candidate, live, backup_dir, bad_manifest)

    notes = " ".join(raised.value.__notes__)
    assert "release_promotion_lock" in notes
    assert "OSError" in notes
    assert "errno=5" in notes
    assert "secret" not in notes
    assert private_path not in notes
    assert user_version(live) == 1
    assert candidate.exists()
