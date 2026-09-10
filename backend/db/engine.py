from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_database_engine(url: str | URL) -> AsyncEngine:
    database_url = make_url(url)
    is_sqlite = database_url.get_backend_name() == "sqlite"
    engine = create_async_engine(url, pool_pre_ping=not is_sqlite)

    if is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def set_connection_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

        query = database_url.query
        database = database_url.database
        is_memory = (
            database in {None, "", ":memory:"}
            or query.get("mode", "").lower() == "memory"
        )
        is_read_only = (
            query.get("mode", "").lower() == "ro"
            or query.get("immutable", "").lower() in {"1", "true", "yes", "on"}
        )

        if not is_memory and not is_read_only:

            @event.listens_for(engine.sync_engine, "connect", once=True)
            def initialize_wal(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    row = cursor.fetchone()
                    journal_mode = str(row[0]).lower() if row else ""
                    if journal_mode != "wal":
                        raise RuntimeError(
                            "SQLite WAL initialization failed: "
                            f"journal_mode={journal_mode or 'unknown'}"
                        )
                finally:
                    cursor.close()

    return engine


__all__ = ["create_database_engine"]
