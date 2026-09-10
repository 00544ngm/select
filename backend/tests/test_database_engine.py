from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.db.engine import create_database_engine
from backend.db.session import create_session_factory


class DatabaseTestBase(DeclarativeBase):
    pass


class StoredValue(DatabaseTestBase):
    __tablename__ = "test_stored_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String)


@pytest.mark.asyncio
async def test_sqlite_engine_enables_required_pragmas(tmp_path):
    database_path = tmp_path / "database.sqlite3"
    engine = create_database_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")

    try:
        async with engine.connect() as connection:
            foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
            journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
            busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))
    finally:
        await engine.dispose()

    assert foreign_keys == 1
    assert journal_mode == "wal"
    assert busy_timeout >= 5000


@pytest.mark.asyncio
async def test_session_factory_keeps_objects_available_after_commit(tmp_path):
    database_path = tmp_path / "sessions.sqlite3"
    engine = create_database_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    factory = create_session_factory(engine)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(DatabaseTestBase.metadata.create_all)
        async with factory() as session:
            stored = StoredValue(value="available")
            session.add(stored)
            await session.commit()

            assert stored.id is not None
            assert stored.value == "available"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_memory_sqlite_skips_wal_but_enables_connection_pragmas():
    engine = create_database_engine("sqlite+aiosqlite:///:memory:")

    try:
        async with engine.connect() as connection:
            foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
            journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
            busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))
    finally:
        await engine.dispose()

    assert foreign_keys == 1
    assert journal_mode == "memory"
    assert busy_timeout >= 5000


def test_non_sqlite_engine_enables_pre_ping_without_sqlite_listeners():
    async_engine = MagicMock()
    async_engine.sync_engine = MagicMock()

    with (
        patch("backend.db.engine.create_async_engine", return_value=async_engine) as create,
        patch("backend.db.engine.event.listens_for") as listens_for,
    ):
        result = create_database_engine("postgresql+asyncpg://user:pass@localhost/db")

    assert result is async_engine
    create.assert_called_once_with(
        "postgresql+asyncpg://user:pass@localhost/db",
        pool_pre_ping=True,
    )
    listens_for.assert_not_called()


def test_file_sqlite_registers_wal_initialization_only_once():
    async_engine = MagicMock()
    async_engine.sync_engine = MagicMock()

    with (
        patch("backend.db.engine.create_async_engine", return_value=async_engine),
        patch("backend.db.engine.event.listens_for") as listens_for,
    ):
        listens_for.side_effect = lambda *_args, **_kwargs: lambda function: function
        create_database_engine("sqlite+aiosqlite:///database.sqlite3")

    assert listens_for.call_count == 2
    assert listens_for.call_args_list[0].kwargs == {}
    assert listens_for.call_args_list[1].kwargs == {"once": True}


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:///file:database.sqlite3?mode=ro&uri=true",
        "sqlite+aiosqlite:///file:database.sqlite3?immutable=true&uri=true",
    ],
)
def test_read_only_sqlite_skips_wal_initialization(url):
    async_engine = MagicMock()
    async_engine.sync_engine = MagicMock()

    with (
        patch("backend.db.engine.create_async_engine", return_value=async_engine),
        patch("backend.db.engine.event.listens_for") as listens_for,
    ):
        listens_for.side_effect = lambda *_args, **_kwargs: lambda function: function
        create_database_engine(url)

    listens_for.assert_called_once_with(async_engine.sync_engine, "connect")


def test_wal_initialization_rejects_non_wal_result():
    async_engine = MagicMock()
    async_engine.sync_engine = MagicMock()
    registered_listeners = []

    def capture_listener(*_args, **_kwargs):
        def register(function):
            registered_listeners.append(function)
            return function

        return register

    with (
        patch("backend.db.engine.create_async_engine", return_value=async_engine),
        patch("backend.db.engine.event.listens_for", side_effect=capture_listener),
    ):
        create_database_engine("sqlite+aiosqlite:///database.sqlite3")

    cursor = MagicMock()
    cursor.fetchone.return_value = ("delete",)
    dbapi_connection = MagicMock()
    dbapi_connection.cursor.return_value = cursor

    with pytest.raises(RuntimeError, match="journal_mode=delete"):
        registered_listeners[1](dbapi_connection, MagicMock())

    cursor.close.assert_called_once_with()
