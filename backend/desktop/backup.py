from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from backend.desktop.migration.manifest import MigrationManifest
from backend.desktop.migration.validator import (
    MigrationValidationError,
    candidate_fingerprint,
    validate_candidate,
)

T = TypeVar("T")


class MigrationPathError(RuntimeError):
    """A promotion path falls outside the owned candidate contract."""


class InsufficientDiskSpaceError(RuntimeError):
    """The old live database cannot be backed up safely."""


class LiveDatabaseBusyError(RuntimeError):
    """The live database still has an active writer."""


class PromotionInProgressError(RuntimeError):
    """A database promotion currently excludes new writers."""


class DesktopMigrationIOError(RuntimeError):
    """A sanitized filesystem error raised during migration promotion."""

    def __init__(self, stage: str, error: OSError) -> None:
        super().__init__("desktop database migration I/O failed")
        self.stage = stage
        errno = getattr(error, "errno", None)
        suffix = f" errno={errno}" if errno is not None else ""
        self.add_note(f"{stage}: {type(error).__name__}{suffix}")


class DesktopMigrationDatabaseError(RuntimeError):
    """A sanitized SQLite error raised during migration promotion."""


@dataclass(frozen=True)
class PromotionResult:
    backup_file: Path | None


def _io(stage: str, operation: Callable[..., T], *args, **kwargs) -> T:
    try:
        return operation(*args, **kwargs)
    except OSError as exc:
        raise DesktopMigrationIOError(stage, exc) from None


def _resolve_path(path: Path) -> Path:
    return path.resolve()


def _is_file(path: Path) -> bool:
    return path.is_file()


def _path_exists(path: Path) -> bool:
    return path.exists()


def _ensure_lock_byte(descriptor: int) -> None:
    if os.fstat(descriptor).st_size == 0:
        os.write(descriptor, b"\0")


def _expected_candidate(live: Path) -> Path:
    return live.with_suffix(".candidate.db")


def _validate_owned_paths(candidate: Path, live: Path) -> None:
    resolved_candidate = _io("resolve_candidate", _resolve_path, candidate)
    resolved_expected = _io(
        "resolve_expected_candidate",
        _resolve_path,
        _expected_candidate(live),
    )
    resolved_live = _io("resolve_live", _resolve_path, live)
    if resolved_candidate != resolved_expected:
        raise MigrationPathError("candidate path does not match live database")
    if resolved_candidate == resolved_live:
        raise MigrationPathError("candidate path must differ from live database")


def _lock_file(live: Path) -> Path:
    return live.with_suffix(".promotion.lock")


def _acquire_file_lock(descriptor: int, *, blocking: bool) -> None:
    import msvcrt

    os.lseek(descriptor, 0, os.SEEK_SET)
    mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
    msvcrt.locking(descriptor, mode, 1)


def _release_file_lock(descriptor: int) -> None:
    import msvcrt

    os.lseek(descriptor, 0, os.SEEK_SET)
    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


@contextmanager
def database_write_guard(live: Path, *, blocking: bool = True):
    descriptor: int | None = None
    locked = False
    body_error: BaseException | None = None
    try:
        descriptor = _io(
            "open_promotion_lock",
            os.open,
            _lock_file(live),
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        _io("initialize_promotion_lock", _ensure_lock_byte, descriptor)
        try:
            _io(
                "acquire_promotion_lock",
                _acquire_file_lock,
                descriptor,
                blocking=blocking,
            )
        except DesktopMigrationIOError as error:
            if not blocking and any("errno=13" in note for note in error.__notes__):
                raise PromotionInProgressError(
                    "database promotion is in progress"
                ) from None
            raise
        locked = True
        yield
    except BaseException as error:  # noqa: BLE001 - lock cleanup includes cancellation
        body_error = error
    finally:
        cleanup_error: DesktopMigrationIOError | None = None
        if descriptor is not None and locked:
            try:
                _io("release_promotion_lock", _release_file_lock, descriptor)
            except DesktopMigrationIOError as error:
                cleanup_error = error
        if descriptor is not None:
            try:
                _io("close_promotion_lock", os.close, descriptor)
            except DesktopMigrationIOError as error:
                if cleanup_error is None:
                    cleanup_error = error
                else:
                    cleanup_error.add_note(error.__notes__[0])
        if body_error is not None:
            if cleanup_error is not None:
                for note in cleanup_error.__notes__:
                    body_error.add_note(note)
            raise body_error.with_traceback(body_error.__traceback__)
        if cleanup_error is not None:
            raise cleanup_error


def _new_backup_path(backup_dir: Path, live: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return backup_dir / f"{live.stem}.pre-migration-{timestamp}-{uuid4().hex}.db"


def _make_backup_directory(backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)


def _available_disk_space(backup_dir: Path) -> int:
    return int(shutil.disk_usage(backup_dir).free)


def _sidecar_paths(live: Path) -> tuple[Path, Path]:
    return (
        live.with_name(f"{live.name}-wal"),
        live.with_name(f"{live.name}-shm"),
    )


def _required_backup_space(live: Path) -> int:
    required = live.stat().st_size
    wal, _shm = _sidecar_paths(live)
    if wal.exists():
        required += wal.stat().st_size
    return required


def _claim_backup(destination: Path) -> None:
    descriptor = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(descriptor)


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _sqlite_backup(live: Path, destination: Path) -> None:
    guard: sqlite3.Connection | None = None
    source: sqlite3.Connection | None = None
    target: sqlite3.Connection | None = None
    primary_error: BaseException | None = None
    try:
        _claim_backup(destination)
        guard = sqlite3.connect(live, timeout=0, isolation_level=None)
        guard.execute("PRAGMA busy_timeout=0")
        try:
            guard.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            raise LiveDatabaseBusyError(
                "live database writes must be stopped before migration"
            ) from None
        source = sqlite3.connect(
            f"file:{live.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=0,
        )
        target = sqlite3.connect(destination)
        source.backup(target)
        target.commit()
    except (LiveDatabaseBusyError, OSError) as error:
        primary_error = error
    except sqlite3.DatabaseError:
        primary_error = DesktopMigrationDatabaseError("database backup failed")
    finally:
        cleanup_errors: list[BaseException] = []
        for connection in (target, source):
            if connection is not None:
                try:
                    _close_connection(connection)
                except (OSError, sqlite3.DatabaseError) as error:
                    cleanup_errors.append(error)
        if guard is not None:
            if guard.in_transaction:
                try:
                    guard.rollback()
                except (OSError, sqlite3.DatabaseError) as error:
                    cleanup_errors.append(error)
            try:
                _close_connection(guard)
            except (OSError, sqlite3.DatabaseError) as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            sanitized = DesktopMigrationIOError(
                "connection_cleanup",
                cleanup_errors[0]
                if isinstance(cleanup_errors[0], OSError)
                else OSError("sqlite connection cleanup failed"),
            )
            if primary_error is not None:
                for note in sanitized.__notes__:
                    primary_error.add_note(note)
            else:
                primary_error = sanitized
    if primary_error is not None:
        raise primary_error


def _close_connection(connection: sqlite3.Connection) -> None:
    connection.close()


def _checkpoint_live(live: Path) -> None:
    connection: sqlite3.Connection | None = None
    primary_error: BaseException | None = None
    try:
        connection = sqlite3.connect(live, timeout=0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=0")
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result is not None and int(result[0]) != 0:
            raise LiveDatabaseBusyError(
                "live database writes must be stopped before migration"
            )
    except LiveDatabaseBusyError as error:
        primary_error = error
    except sqlite3.DatabaseError:
        primary_error = DesktopMigrationDatabaseError("database checkpoint failed")
    finally:
        if connection is not None:
            try:
                _close_connection(connection)
            except (OSError, sqlite3.DatabaseError) as error:
                cleanup_error = DesktopMigrationIOError(
                    "connection_cleanup",
                    error if isinstance(error, OSError) else OSError("cleanup failed"),
                )
                if primary_error is not None:
                    primary_error.add_note(cleanup_error.__notes__[0])
                else:
                    primary_error = cleanup_error
    if primary_error is not None:
        raise primary_error


def _remove_sidecar(sidecar: Path) -> None:
    sidecar.unlink(missing_ok=True)


def _create_backup(live: Path, backup_dir: Path) -> Path:
    _io("mkdir_backup", _make_backup_directory, backup_dir)
    required = _io("stat_live", _required_backup_space, live)
    free = _io("disk_usage", _available_disk_space, backup_dir)
    if free < required:
        raise InsufficientDiskSpaceError("insufficient disk space for database backup")
    destination = _new_backup_path(backup_dir, live)
    try:
        _io("sqlite_backup", _sqlite_backup, live, destination)
        _io("fsync_backup", _fsync_file, destination)
    except BaseException as error:
        try:
            _io("cleanup_partial_backup", destination.unlink, missing_ok=True)
        except DesktopMigrationIOError as cleanup_error:
            for note in cleanup_error.__notes__:
                error.add_note(note)
        raise
    return destination


def _prepare_live_for_replace(live: Path) -> None:
    _checkpoint_live(live)
    for sidecar in _sidecar_paths(live):
        _io("remove_sidecar", _remove_sidecar, sidecar)


def _candidate_has_sidecars(candidate: Path) -> bool:
    return any(_io("candidate_sidecar_exists", _path_exists, path) for path in _sidecar_paths(candidate))


def _prepare_candidate(candidate: Path) -> None:
    if not _io("candidate_is_file", _is_file, candidate):
        raise MigrationValidationError(("candidate_missing",))
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(candidate, timeout=0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=0")
        connection.execute("BEGIN IMMEDIATE")
        connection.rollback()
    except sqlite3.DatabaseError:
        raise MigrationValidationError(("candidate_connections_not_closed",)) from None
    finally:
        if connection is not None:
            try:
                _close_connection(connection)
            except OSError as error:
                raise DesktopMigrationIOError("connection_cleanup", error) from None
            except sqlite3.DatabaseError:
                raise DesktopMigrationDatabaseError(
                    "candidate connection cleanup failed"
                ) from None
    _checkpoint_live(candidate)
    connection = None
    try:
        connection = sqlite3.connect(candidate, timeout=0, isolation_level=None)
        mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
        if mode is None or str(mode[0]).lower() != "delete":
            raise MigrationValidationError(("candidate_single_file_mode_failed",))
    except MigrationValidationError:
        raise
    except sqlite3.DatabaseError:
        raise MigrationValidationError(("candidate_single_file_mode_failed",)) from None
    finally:
        if connection is not None:
            try:
                _close_connection(connection)
            except OSError as error:
                raise DesktopMigrationIOError("connection_cleanup", error) from None
            except sqlite3.DatabaseError:
                raise DesktopMigrationDatabaseError(
                    "candidate connection cleanup failed"
                ) from None
    for sidecar in _sidecar_paths(candidate):
        _io("remove_candidate_sidecar", _remove_sidecar, sidecar)
    if _candidate_has_sidecars(candidate):
        raise MigrationValidationError(("candidate_sidecar_present",))


def promote_candidate(
    candidate: Path,
    live: Path,
    backup_dir: Path,
    manifest: MigrationManifest,
) -> PromotionResult:
    with database_write_guard(live, blocking=False):
        _validate_owned_paths(candidate, live)
        _prepare_candidate(candidate)
        validation = validate_candidate(candidate, manifest)
        if not validation.ok:
            raise MigrationValidationError(validation.errors)
        current_fingerprint = _io(
            "stat_candidate",
            candidate_fingerprint,
            candidate,
        )
        if current_fingerprint != validation.candidate_fingerprint:
            raise MigrationValidationError(("candidate changed after validation",))
        if _candidate_has_sidecars(candidate):
            raise MigrationValidationError(("candidate_sidecar_changed",))

        backup_file: Path | None = None
        if _io("live_exists", _path_exists, live):
            backup_file = _create_backup(live, backup_dir)
            _prepare_live_for_replace(live)
        else:
            for sidecar in _sidecar_paths(live):
                _io("remove_sidecar", _remove_sidecar, sidecar)

        final_fingerprint = _io("stat_candidate", candidate_fingerprint, candidate)
        if final_fingerprint != validation.candidate_fingerprint:
            raise MigrationValidationError(("candidate changed after validation",))
        if _candidate_has_sidecars(candidate):
            raise MigrationValidationError(("candidate_sidecar_changed",))
        _io("replace_live", os.replace, candidate, live)
        return PromotionResult(backup_file=backup_file)


__all__ = [
    "DesktopMigrationDatabaseError",
    "DesktopMigrationIOError",
    "InsufficientDiskSpaceError",
    "LiveDatabaseBusyError",
    "MigrationPathError",
    "PromotionInProgressError",
    "PromotionResult",
    "database_write_guard",
    "promote_candidate",
]
