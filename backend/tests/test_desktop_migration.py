from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.db.engine import create_database_engine
from backend.db.models import (
    AnalysisJob,
    Artifact,
    JobProduct,
    ProductSnapshot,
    ProviderConfiguration,
    ProviderModelValidation,
)
from backend.db.session import create_session_factory
from backend.desktop.migration.exporter import TABLE_ORDER, TABLES, order_analysis_jobs
from backend.desktop.migration.importer import (
    MigrationCleanupError,
    _claim_candidate,
    _diagnostic_note,
    _migration_paths,
    migrate_read_only,
)
from backend.desktop.migration.manifest import build_manifest
from backend.desktop.migrations import upgrade_database_async


def sqlite_url(path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


async def seed_all_tables(source_url: str) -> dict[str, object]:
    await upgrade_database_async(source_url)
    engine = create_database_engine(source_url)
    factory = create_session_factory(engine)
    job_id, snapshot_id, provider_id = uuid4(), uuid4(), uuid4()
    artifact_id, link_id, validation_id = uuid4(), uuid4(), uuid4()
    timestamp = datetime(2026, 8, 2, 7, 8, 9, tzinfo=timezone.utc)
    result_payload = {"status": "KNOWN", "nested": {"score": 97}, "items": [1, 2]}
    ciphertext = "enc:v1:TOP-SECRET-CIPHERTEXT"
    async with factory() as session, session.begin():
        await session.execute(insert(AnalysisJob).values(
            id=job_id, name=None, mode="single", status="completed",
            request_payload={"url": "https://example.test/item"},
            result_payload=result_payload, progress=100, error_code=None,
            error_message=None, retry_of_id=None, version=4,
            created_at=timestamp, updated_at=timestamp,
        ))
        await session.execute(insert(ProductSnapshot).values(
            id=snapshot_id, product_url="https://example.test/item", platform="test",
            scraped_data={"title": "sample", "nullable": None}, scraped_at=timestamp,
        ))
        await session.execute(insert(JobProduct).values(
            id=link_id, job_id=job_id, product_snapshot_id=snapshot_id,
            role="primary", position=0,
        ))
        await session.execute(insert(Artifact).values(
            id=artifact_id, job_id=job_id, kind="json", path="result.json",
            size=123, checksum="abc", created_at=timestamp,
        ))
        await session.execute(insert(ProviderConfiguration).values(
            id=provider_id, slug="provider-one", provider_type="custom",
            api_protocol="openai", display_name="Provider One", base_url=None,
            default_model="model-a", supported_models=["model-a", "model-b"],
            encrypted_api_key=ciphertext, api_key_last4="1234", is_enabled=True,
            last_test_status="success", last_tested_at=timestamp,
            last_test_message=None, created_at=timestamp, updated_at=timestamp,
        ))
        await session.execute(insert(ProviderModelValidation).values(
            id=validation_id, provider_slug="provider-one", api_protocol="openai",
            model="model-a", status="valid", error_code=None, message="ok",
            tested_at=timestamp,
        ))
    await engine.dispose()
    return {"job_id": job_id, "timestamp": timestamp, "result": result_payload,
            "ciphertext": ciphertext}


async def database_snapshot(database_url: str) -> dict[str, list[dict[str, object]]]:
    engine = create_database_engine(database_url)
    try:
        async with engine.connect() as connection:
            snapshot = {}
            for table_name in TABLE_ORDER:
                table = TABLES[table_name]
                rows = [dict(row) for row in (await connection.execute(select(table))).mappings()]
                snapshot[table_name] = sorted(rows, key=lambda row: str(row["id"]))
            return snapshot
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_migrates_all_tables_losslessly_without_mutating_source(tmp_path) -> None:
    source_file = tmp_path / "source.db"
    target_file = tmp_path / "desktop.db"
    source_url = sqlite_url(source_file)
    expected = await seed_all_tables(source_url)
    before = source_file.read_bytes()
    source_snapshot = await database_snapshot(source_url)

    manifest = await migrate_read_only(source_url, target_file)

    candidate = target_file.with_suffix(".candidate.db")
    assert candidate.exists()
    assert manifest.source_counts == manifest.target_counts == {
        table: 1 for table in TABLE_ORDER
    }
    assert manifest.candidate_file == candidate
    assert source_file.read_bytes() == before
    assert await database_snapshot(sqlite_url(candidate)) == source_snapshot
    assert await database_snapshot(source_url) == source_snapshot
    engine = create_database_engine(sqlite_url(candidate))
    factory = create_session_factory(engine)
    async with factory() as session:
        job = (await session.execute(select(AnalysisJob))).scalar_one()
        provider = (await session.execute(select(ProviderConfiguration))).scalar_one()
        assert job.id == expected["job_id"]
        assert job.result_payload == expected["result"]
        assert job.created_at.replace(tzinfo=timezone.utc) == expected["timestamp"]
        assert provider.supported_models == ["model-a", "model-b"]
        assert provider.encrypted_api_key == expected["ciphertext"]
    await engine.dispose()
    serialized = json.dumps(manifest.to_dict())
    assert "TOP-SECRET" not in serialized
    assert "encrypted_api_key" not in serialized
    assert "result_payload" not in serialized


@pytest.mark.asyncio
async def test_existing_candidate_is_rejected_without_overwrite(tmp_path) -> None:
    source_url = sqlite_url(tmp_path / "source.db")
    await seed_all_tables(source_url)
    target_file = tmp_path / "desktop.db"
    candidate = target_file.with_suffix(".candidate.db")
    candidate.write_bytes(b"do-not-overwrite")
    with pytest.raises(FileExistsError, match="candidate"):
        await migrate_read_only(source_url, target_file)
    assert candidate.read_bytes() == b"do-not-overwrite"


@pytest.mark.asyncio
async def test_failed_import_has_no_partial_commit_or_manifest(tmp_path, monkeypatch) -> None:
    source_url = sqlite_url(tmp_path / "source.db")
    await seed_all_tables(source_url)
    target_file = tmp_path / "desktop.db"
    from backend.desktop.migration import importer

    original = importer._copy_table
    calls = 0

    async def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected import failure")
        return await original(*args, **kwargs)

    monkeypatch.setattr(importer, "_copy_table", fail_second)
    with pytest.raises(RuntimeError, match="injected"):
        await migrate_read_only(source_url, target_file)
    failed = target_file.with_suffix(".candidate.failed.db")
    assert failed.exists()
    with sqlite3.connect(failed) as connection:
        assert connection.execute("SELECT count(*) FROM analysis_jobs").fetchone() == (0,)


@pytest.mark.asyncio
async def test_both_engines_are_disposed(tmp_path, monkeypatch) -> None:
    source_url = sqlite_url(tmp_path / "source.db")
    await seed_all_tables(source_url)
    from backend.desktop.migration import importer

    real_create = importer.create_database_engine
    engines = []
    disposed: set[int] = set()
    real_dispose = AsyncEngine.dispose

    async def tracked_dispose(engine, *args, **kwargs):
        disposed.add(id(engine))
        await real_dispose(engine, *args, **kwargs)

    monkeypatch.setattr(AsyncEngine, "dispose", tracked_dispose)

    def tracked_create(url):
        engine = real_create(url)
        engines.append(engine)
        return engine

    monkeypatch.setattr(importer, "create_database_engine", tracked_create)
    await migrate_read_only(source_url, tmp_path / "desktop.db")
    assert len(engines) == 2
    assert {id(engine) for engine in engines} <= disposed


def test_postgresql_source_transaction_is_declared_read_only() -> None:
    from backend.desktop.migration.exporter import install_source_read_only_guard

    statements: list[str] = []

    class Connection:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def exec_driver_sql(self, statement: str) -> None:
            statements.append(statement)

    install_source_read_only_guard(Connection())
    assert statements == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    ]


@pytest.mark.asyncio
async def test_build_manifest_detects_count_mismatch(tmp_path) -> None:
    source_url = sqlite_url(tmp_path / "source.db")
    target_url = sqlite_url(tmp_path / "target.db")
    await seed_all_tables(source_url)
    await upgrade_database_async(target_url)
    source_engine = create_database_engine(source_url)
    target_engine = create_database_engine(target_url)
    try:
        with pytest.raises(ValueError, match="count mismatch"):
            await build_manifest(
                {table: 1 for table in TABLE_ORDER},
                target_engine,
                tmp_path / "target.db",
            )
    finally:
        await source_engine.dispose()
        await target_engine.dispose()


@pytest.mark.parametrize(
    ("target_name", "candidate_name", "failed_name"),
    [
        ("desktop", "desktop.candidate.db", "desktop.candidate.failed.db"),
        ("desktop.db", "desktop.candidate.db", "desktop.candidate.failed.db"),
        ("desktop.backup.db", "desktop.backup.candidate.db", "desktop.backup.candidate.failed.db"),
    ],
)
def test_candidate_paths_follow_path_with_suffix_contract(
    tmp_path, target_name, candidate_name, failed_name
) -> None:
    candidate, failed = _migration_paths(tmp_path / target_name)
    assert candidate == tmp_path / candidate_name
    assert failed == tmp_path / failed_name


@pytest.mark.asyncio
async def test_existing_failed_candidate_is_rejected(tmp_path) -> None:
    target = tmp_path / "desktop.db"
    _, failed = _migration_paths(target)
    failed.write_bytes(b"previous failure")
    with pytest.raises(FileExistsError, match="failed"):
        await migrate_read_only("sqlite+aiosqlite:///:memory:", target)
    assert failed.read_bytes() == b"previous failure"


@pytest.mark.asyncio
async def test_upgrade_failure_marks_created_candidate_failed(tmp_path, monkeypatch) -> None:
    from backend.desktop.migration import importer

    target = tmp_path / "desktop.db"
    candidate, failed = _migration_paths(target)

    async def failing_upgrade(*_args, **_kwargs):
        candidate.write_bytes(b"partial schema")
        raise RuntimeError("upgrade failed")

    monkeypatch.setattr(importer, "upgrade_database_async", failing_upgrade)
    with pytest.raises(RuntimeError, match="upgrade failed"):
        await migrate_read_only("sqlite+aiosqlite:///:memory:", target)
    assert not candidate.exists()
    assert failed.read_bytes() == b"partial schema"


@pytest.mark.asyncio
async def test_target_engine_creation_failure_disposes_source(tmp_path, monkeypatch) -> None:
    from backend.desktop.migration import importer

    source_engine = Mock()
    source_engine.dispose = AsyncMock()
    monkeypatch.setattr(importer, "upgrade_database_async", AsyncMock())
    monkeypatch.setattr(
        importer,
        "create_database_engine",
        Mock(side_effect=[source_engine, RuntimeError("target engine failed")]),
    )
    with pytest.raises(RuntimeError, match="target engine failed"):
        await migrate_read_only("postgresql+asyncpg://source", tmp_path / "desktop.db")
    source_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_attempts_both_engines_and_preserves_migration_error(
    tmp_path, monkeypatch
) -> None:
    source_url = sqlite_url(tmp_path / "source.db")
    await seed_all_tables(source_url)
    from backend.desktop.migration import importer

    engines = []
    real_create = importer.create_database_engine
    real_dispose = AsyncEngine.dispose
    disposed: list[int] = []

    def create(url):
        engine = real_create(url)
        engines.append(engine)
        return engine

    async def dispose(engine, *args, **kwargs):
        disposed.append(id(engine))
        await real_dispose(engine, *args, **kwargs)
        if engines and engine is engines[0]:
            raise RuntimeError("cleanup failed")

    async def fail_copy(*_args, **_kwargs):
        raise ValueError("copy failed")

    monkeypatch.setattr(importer, "create_database_engine", create)
    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    monkeypatch.setattr(importer, "_copy_table", fail_copy)
    target = tmp_path / "desktop.db"
    with pytest.raises(ValueError, match="copy failed") as raised:
        await migrate_read_only(source_url, target)
    assert {id(engine) for engine in engines} <= set(disposed)
    assert _migration_paths(target)[1].exists()
    notes = " ".join(raised.value.__notes__)
    assert "engine cleanup" in notes
    assert "RuntimeError" in notes
    assert "cleanup failed" not in notes
    assert str(tmp_path) not in notes


@pytest.mark.asyncio
async def test_cleanup_failure_after_success_marks_candidate_failed(
    tmp_path, monkeypatch
) -> None:
    source_url = sqlite_url(tmp_path / "source.db")
    await seed_all_tables(source_url)
    from backend.desktop.migration import importer

    engines = []
    real_create = importer.create_database_engine
    real_dispose = AsyncEngine.dispose

    def create(url):
        engine = real_create(url)
        engines.append(engine)
        return engine

    async def dispose(engine, *args, **kwargs):
        await real_dispose(engine, *args, **kwargs)
        if engines and engine is engines[0]:
            raise RuntimeError("cleanup failed")

    monkeypatch.setattr(importer, "create_database_engine", create)
    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    target = tmp_path / "desktop.db"
    with pytest.raises(MigrationCleanupError, match="cleanup failed") as raised:
        await migrate_read_only(source_url, target)
    candidate, failed = _migration_paths(target)
    assert not candidate.exists()
    assert failed.exists()
    assert "engine cleanup: RuntimeError" in " ".join(raised.value.__notes__)


def test_analysis_jobs_are_stably_topologically_sorted() -> None:
    root, child, grandchild = uuid4(), uuid4(), uuid4()
    rows = [
        {"id": grandchild, "retry_of_id": child},
        {"id": child, "retry_of_id": root},
        {"id": root, "retry_of_id": None},
    ]
    assert [row["id"] for row in order_analysis_jobs(rows)] == [root, child, grandchild]


def test_analysis_job_sort_rejects_missing_parent_and_cycle() -> None:
    first, second, missing = uuid4(), uuid4(), uuid4()
    with pytest.raises(ValueError, match="missing retry parent"):
        order_analysis_jobs([{"id": first, "retry_of_id": missing}])
    with pytest.raises(ValueError, match="cycle"):
        order_analysis_jobs(
            [
                {"id": first, "retry_of_id": second},
                {"id": second, "retry_of_id": first},
            ]
        )


def test_candidate_claim_is_atomic_and_does_not_overwrite(tmp_path) -> None:
    candidate = tmp_path / "desktop.candidate.db"
    _claim_candidate(candidate)
    candidate.write_bytes(b"owned by first migration")
    with pytest.raises(FileExistsError):
        _claim_candidate(candidate)
    assert candidate.read_bytes() == b"owned by first migration"


def test_analysis_job_sort_handles_large_chain() -> None:
    ids = [uuid4() for _ in range(5000)]
    rows = [
        {"id": job_id, "retry_of_id": ids[index - 1] if index else None}
        for index, job_id in reversed(list(enumerate(ids)))
    ]
    assert [row["id"] for row in order_analysis_jobs(rows)] == ids


def test_manifest_serialization_hides_absolute_candidate_path(tmp_path) -> None:
    from backend.desktop.migration.manifest import MigrationManifest

    manifest = MigrationManifest(
        source_counts={},
        target_counts={},
        candidate_file=tmp_path / "private" / "desktop.candidate.db",
        schema_version="head",
        created_at=datetime.now(timezone.utc),
    )
    assert manifest.to_dict()["candidate_file"] == "desktop.candidate.db"


def test_cleanup_error_type_is_explicit() -> None:
    assert issubclass(MigrationCleanupError, RuntimeError)


def test_diagnostic_note_is_sanitized() -> None:
    error = OSError(13, "secret-message", "C:/private/user/candidate.db")
    note = _diagnostic_note("failed rename", error)
    assert note == "failed rename: PermissionError errno=13"
    assert "secret" not in note
    assert "private" not in note
