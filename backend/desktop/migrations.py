from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "migrations" / "alembic.ini"


def upgrade_database(database_url: str | URL, revision: str = "head") -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("path_separator", "os")
    config.attributes["database_connection_url"] = database_url
    config.set_main_option("sqlalchemy.url", str(database_url).replace("%", "%%"))
    config.attributes["database_url_explicit"] = True
    command.upgrade(config, revision)


async def upgrade_database_async(
    database_url: str | URL,
    revision: str = "head",
) -> None:
    await asyncio.to_thread(upgrade_database, database_url, revision)


__all__ = ["ALEMBIC_INI", "upgrade_database", "upgrade_database_async"]
