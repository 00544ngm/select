from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.core.config import settings

try:
    from loguru import logger
except ModuleNotFoundError:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    class _StdlibLoggerAdapter:
        def __init__(self) -> None:
            self._logger = logging.getLogger("walmart_aba")

        def debug(self, message: str, *args: object) -> None:
            self._logger.debug(self._format(message, *args))

        def info(self, message: str, *args: object) -> None:
            self._logger.info(self._format(message, *args))

        def warning(self, message: str, *args: object) -> None:
            self._logger.warning(self._format(message, *args))

        def error(self, message: str, *args: object) -> None:
            self._logger.error(self._format(message, *args))

        @staticmethod
        def _format(message: str, *args: object) -> str:
            if not args:
                return message
            try:
                return message.format(*args)
            except Exception:
                return f"{message} {' '.join(str(arg) for arg in args)}"

    logger = _StdlibLoggerAdapter()


def setup_logger() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    if not hasattr(logger, "remove"):
        return

    logger.remove()

    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan> | {message}",
    )

    logger.add(
        log_dir / "app.log",
        level="INFO",
        rotation="10 MB",
        retention=7,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name} | {message}",
    )

    logger.add(
        log_dir / "error.log",
        level="ERROR",
        rotation="10 MB",
        retention=30,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name} | {message}",
    )

    logger.add(
        log_dir / "debug.log",
        level="DEBUG",
        rotation="5 MB",
        retention=3,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name} | {message}",
    )


__all__ = ["setup_logger"]
