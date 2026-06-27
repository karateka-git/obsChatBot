from __future__ import annotations

import argparse
import logging
import sqlite3
import tempfile
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .database import connect_database
from .migration_runner import MigrationError, apply_migrations
from .smoke import SQLiteSmokeError, run_sqlite_smoke


def configure_logging() -> None:
    """Настраивает единый формат логов приложения."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Читает аргументы командной строки приложения."""
    parser = argparse.ArgumentParser(prog="obs-chat-bot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--healthcheck",
        action="store_true",
        help="Validate configuration and writable data directory, then exit.",
    )
    mode.add_argument(
        "--sqlite-smoke",
        action="store_true",
        help="Run SQLite migrations and repository smoke scenario, then exit.",
    )
    return parser.parse_args()


def main() -> int:
    """Запускает выбранный режим приложения и возвращает exit code."""
    args = parse_args()
    configure_logging()
    logger = logging.getLogger("obs_chat_bot")

    logger.info("Starting obsChatBot %s", __version__)

    if args.sqlite_smoke:
        return run_sqlite_smoke_command(logger)

    try:
        config = load_config()
    except ConfigError as error:
        logger.error("Configuration error: %s", error)
        return 2

    config.data_dir.mkdir(parents=True, exist_ok=True)

    if args.healthcheck:
        return run_healthcheck(config.database_path, logger)

    for key, value in config.safe_summary().items():
        logger.info("Config %s: %s", key, value)

    logger.info("Data directory: %s", config.data_dir.resolve())

    if not initialize_database(config.database_path, logger):
        return 1

    logger.info("Configuration is ready")

    return 0


def run_healthcheck(database_path: Path, logger: logging.Logger) -> int:
    """Проверяет доступность каталога данных и соединения с SQLite.

    Args:
        database_path: Путь к рабочему файлу SQLite.
        logger: Logger для диагностических сообщений.

    Returns:
        Ноль при успехе, иначе единицу.
    """
    try:
        with tempfile.NamedTemporaryFile(
            dir=database_path.parent,
            prefix="health-",
            delete=True,
        ):
            pass
    except OSError as error:
        logger.error("Health check failed: data directory is not writable: %s", error)
        return 1

    if not check_database(database_path, logger):
        return 1

    logger.info("Health check passed")
    return 0


def check_database(database_path: Path, logger: logging.Logger) -> bool:
    """Проверяет возможность открыть рабочую SQLite-базу.

    Args:
        database_path: Путь к рабочему файлу SQLite.
        logger: Logger для диагностических сообщений.

    Returns:
        `True`, если соединение успешно открыто.
    """
    try:
        with connect_database(database_path):
            pass
    except (OSError, sqlite3.Error) as error:
        logger.error("Database connection failed: %s", error)
        return False

    logger.info("Database connection is ready")
    return True


def initialize_database(database_path: Path, logger: logging.Logger) -> bool:
    """Открывает рабочую базу и применяет ожидающие миграции.

    Args:
        database_path: Путь к рабочему файлу SQLite.
        logger: Logger для диагностических сообщений.

    Returns:
        `True`, если база готова к работе.
    """
    try:
        with connect_database(database_path) as connection:
            applied = apply_migrations(connection)
    except (MigrationError, OSError, sqlite3.Error) as error:
        logger.error("Database initialization failed: %s", error)
        return False

    for migration in applied:
        logger.info("Applied database migration: %s", migration.name)

    if not applied:
        logger.info("Database schema is up to date")

    logger.info("Database connection is ready")
    return True


def run_sqlite_smoke_command(logger: logging.Logger) -> int:
    """Запускает SQLite smoke-сценарий как команду приложения.

    Args:
        logger: Logger для результата проверки.

    Returns:
        Ноль при успехе, иначе единицу.
    """
    try:
        run_sqlite_smoke()
    except SQLiteSmokeError as error:
        logger.error("%s", error)
        return 1

    logger.info("SQLite smoke scenario passed")
    return 0
