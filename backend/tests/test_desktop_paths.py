from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from backend.config import BackendSettings, database_connection_url
from backend.desktop.paths import DesktopPaths

SERVER_DATABASE_URL = (
    "postgresql+asyncpg://bundling:bundling@127.0.0.1:5432/bundling"
)


def make_settings(**overrides):
    return BackendSettings(_env_file=None, **overrides)


def test_desktop_paths_use_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = DesktopPaths.for_current_user()
    assert paths.data_dir == tmp_path / "组合选品控制台"
    assert paths.database_file == paths.data_dir / "data" / "bundling.db"
    assert paths.backup_dir == paths.data_dir / "backups"
    assert paths.log_dir == paths.data_dir / "logs"
    assert paths.artifact_dir == paths.data_dir / "artifacts"
    assert paths.temp_dir == paths.data_dir / "temp"


def test_desktop_artifact_dir_accepts_special_characters(tmp_path):
    artifact_dir = tmp_path / "员工 #100%" / "artifacts"

    settings = make_settings(runtime_mode="desktop", artifact_dir=artifact_dir)

    assert settings.artifact_dir == artifact_dir


def test_desktop_database_path_keeps_hash_percent_spaces_and_chinese(tmp_path):
    database = tmp_path / "员工 #100%" / "组合品" / "bundling.db"
    settings = make_settings(
        runtime_mode="desktop",
        desktop_database_path=database,
    )

    url = database_connection_url(settings)

    assert url.database == database.resolve().as_posix()


def test_desktop_paths_are_frozen(tmp_path):
    paths = DesktopPaths(data_dir=tmp_path)

    with pytest.raises(FrozenInstanceError):
        paths.data_dir = tmp_path / "other"


def test_desktop_paths_do_not_create_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths = DesktopPaths.for_current_user()

    assert not paths.data_dir.exists()
    assert not paths.database_file.parent.exists()
    assert not paths.backup_dir.exists()


def test_backend_settings_runtime_mode_defaults_to_server(monkeypatch):
    monkeypatch.delenv("RUNTIME_MODE", raising=False)

    assert make_settings().runtime_mode == "server"


def test_backend_settings_accepts_desktop_runtime_mode():
    assert make_settings(runtime_mode="desktop").runtime_mode == "desktop"


def test_backend_settings_rejects_invalid_runtime_mode():
    with pytest.raises(ValidationError):
        make_settings(runtime_mode="invalid")


def test_backend_settings_keeps_server_database_url_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert make_settings().database_url == SERVER_DATABASE_URL
