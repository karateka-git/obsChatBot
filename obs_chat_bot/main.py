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


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="obs-chat-bot")
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Validate configuration and writable data directory, then exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    logger = logging.getLogger("obs_chat_bot")

    logger.info("Starting obsChatBot %s", __version__)

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
    try:
        with connect_database(database_path):
            pass
    except (OSError, sqlite3.Error) as error:
        logger.error("Database connection failed: %s", error)
        return False

    logger.info("Database connection is ready")
    return True


def initialize_database(database_path: Path, logger: logging.Logger) -> bool:
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
