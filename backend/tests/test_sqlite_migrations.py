from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.config import get_backend_settings
from backend.desktop.migrations import (
    ALEMBIC_INI,
    upgrade_database,
    upgrade_database_async,
)


def make_alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("path_separator", "os")
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
        config.attributes["database_url_explicit"] = True
    return config


def current_head() -> str:
    head = ScriptDirectory.from_config(make_alembic_config()).get_current_head()
    assert head is not None
    return head


@pytest.mark.asyncio
async def test_upgrade_database_async_runs_inside_event_loop(tmp_path) -> None:
    database_path = tmp_path / "async-desktop.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    await upgrade_database_async(database_url)

    with sqlite3.connect(database_path) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    assert version == (current_head(),)


def test_upgrade_database_creates_sqlite_schema_at_head(tmp_path) -> None:
    database_path = tmp_path / "desktop.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    upgrade_database(database_url, "head")

    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "analysis_jobs",
            "product_snapshots",
            "job_products",
            "artifacts",
            "provider_configurations",
            "provider_model_validations",
            "local_queue_items",
            "alembic_version",
        } <= table_names

        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        assert version == (current_head(),)

        job_product_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list('job_products')"
        ).fetchall()
        assert {(row[2], row[3], row[4], row[6]) for row in job_product_foreign_keys} == {
            ("analysis_jobs", "job_id", "id", "CASCADE"),
            ("product_snapshots", "product_snapshot_id", "id", "CASCADE"),
        }

        job_product_indexes = connection.execute(
            "PRAGMA index_list('job_products')"
        ).fetchall()
        unique_column_orders = {
            tuple(
                row[2]
                for row in connection.execute(
                    f'PRAGMA index_info("{index_row[1]}")'
                )
            )
            for index_row in job_product_indexes
            if index_row[2] == 1
        }
        assert ("job_id", "role", "position") in unique_column_orders

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "ix_analysis_jobs_status_created",
            "ix_analysis_jobs_mode_created",
            "ix_provider_model_validations_provider_status",
            "ix_local_queue_items_status_created",
        } <= indexes

        provider_columns = {
            row[1]: (row[3], row[4])
            for row in connection.execute(
                "PRAGMA table_info('provider_configurations')"
            )
        }
        validation_columns = {
            row[1]: (row[3], row[4])
            for row in connection.execute(
                "PRAGMA table_info('provider_model_validations')"
            )
        }
        assert provider_columns["validation_revision"] == (1, "'1'")
        assert validation_columns["connection_revision"] == (1, "'1'")
        assert validation_columns["use_count"] == (1, "'0'")
        assert validation_columns["last_used_at"] == (0, None)
        assert validation_columns["last_auto_tested_at"] == (0, None)
        assert validation_columns["transport_mode"] == (0, None)
        assert validation_columns["structured_output_mode"] == (0, None)


def test_upgrade_0011_adds_nullable_openai_compatibility_modes(tmp_path) -> None:
    database_path = tmp_path / "openai-compatibility.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    config = make_alembic_config(database_url)
    command.upgrade(config, "0011")
    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: (row[3], row[4])
            for row in connection.execute(
                "PRAGMA table_info('provider_model_validations')"
            )
        }

    assert columns["transport_mode"] == (0, None)
    assert columns["structured_output_mode"] == (0, None)


def test_upgrade_database_creates_job_model_attempts_schema(tmp_path) -> None:
    database_path = tmp_path / "attempts.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    upgrade_database(database_url, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('job_model_attempts')"
            )
        }
        unique_indexes = {
            tuple(
                column[2]
                for column in connection.execute(
                    f'PRAGMA index_info("{index[1]}")'
                )
            )
            for index in connection.execute(
                "PRAGMA index_list('job_model_attempts')"
            )
            if index[2] == 1
        }

    assert {
        "id",
        "job_id",
        "ordinal",
        "provider",
        "api_protocol",
        "model",
        "status",
        "stage",
        "error_code",
        "error_message",
        "started_at",
        "finished_at",
        "duration_ms",
    } <= columns
    assert ("job_id", "ordinal") in unique_indexes


def test_upgrade_0008_to_0009_preserves_provider_secret_and_model_history(tmp_path) -> None:
    database_path = tmp_path / "upgrade-history.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    config = make_alembic_config(database_url)
    command.upgrade(config, "0008")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO provider_configurations (
                id, slug, provider_type, api_protocol, display_name, base_url,
                default_model, supported_models, encrypted_api_key,
                api_key_last4, is_enabled, last_test_status,
                last_tested_at, last_test_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "11111111111111111111111111111111",
                "custom",
                "openai_compatible",
                "openai",
                "自定义 API",
                "https://example.test/v1",
                "model-a",
                '["model-a"]',
                "encrypted-secret-value",
                "A1B2",
                1,
                "success",
                "2026-08-01 00:00:00",
                "Connection successful",
                "2026-08-01 00:00:00",
                "2026-08-01 00:00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO provider_model_validations (
                id, provider_slug, api_protocol, model, status, error_code,
                message, tested_at, is_selected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "22222222222222222222222222222222",
                "custom",
                "openai",
                "model-a",
                "verified",
                None,
                "结构化验证成功",
                "2026-08-01 00:00:00",
                1,
            ),
        )
        connection.commit()

    command.upgrade(config, "0009")

    with sqlite3.connect(database_path) as connection:
        provider = connection.execute(
            "SELECT encrypted_api_key, validation_revision FROM provider_configurations WHERE slug = 'custom'"
        ).fetchone()
        validation = connection.execute(
            """
            SELECT status, is_selected, connection_revision, use_count,
                   last_used_at, last_auto_tested_at
            FROM provider_model_validations
            WHERE provider_slug = 'custom' AND model = 'model-a'
            """
        ).fetchone()

    assert provider == ("encrypted-secret-value", 1)
    assert validation == ("verified", 1, 1, 0, None, None)


def test_explicit_database_url_overrides_cached_settings(tmp_path, monkeypatch) -> None:
    target_path = tmp_path / "explicit.db"
    polluted_path = tmp_path / "polluted.db"
    target_url = f"sqlite+aiosqlite:///{target_path.as_posix()}"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{polluted_path.as_posix()}",
    )
    get_backend_settings.cache_clear()
    try:
        assert get_backend_settings().database_url.endswith("polluted.db")

        upgrade_database(target_url)
    finally:
        get_backend_settings.cache_clear()

    assert target_path.exists()
    assert not polluted_path.exists()
    with sqlite3.connect(target_path) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    assert version == (current_head(),)


def test_sqlite_can_round_trip_from_head_through_revision_0003(tmp_path) -> None:
    database_path = tmp_path / "round-trip.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    upgrade_database(database_url)

    command.downgrade(make_alembic_config(database_url), "0003")
    with sqlite3.connect(database_path) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        column_names = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('provider_configurations')"
            )
        }
    assert version == ("0003",)
    assert "supported_models" not in column_names
    assert "api_protocol" not in column_names

    upgrade_database(database_url)
    with sqlite3.connect(database_path) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        columns = {
            row[1]: (row[3], row[4])
            for row in connection.execute(
                "PRAGMA table_info('provider_configurations')"
            )
        }
        provider_unique_column_orders = {
            tuple(
                row[2]
                for row in connection.execute(
                    f'PRAGMA index_info("{index_row[1]}")'
                )
            )
            for index_row in connection.execute(
                "PRAGMA index_list('provider_configurations')"
            )
            if index_row[2] == 1
        }

    assert version == (current_head(),)
    assert columns["supported_models"] == (1, None)
    assert columns["api_protocol"] == (1, None)
    assert ("slug",) in provider_unique_column_orders
