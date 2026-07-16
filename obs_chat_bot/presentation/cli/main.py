from __future__ import annotations

import argparse
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Callable

from obs_chat_bot import __version__
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlError,
    ProcessArticleUrlUseCase,
)
from obs_chat_bot.data.extraction.trafilatura_article_extractor import (
    TrafilaturaArticleTextExtractor,
)
from obs_chat_bot.data.config import ConfigError, load_config
from obs_chat_bot.data.http.article_html_fetcher import UrllibArticleHtmlFetcher
from obs_chat_bot.data.sqlite.article_repository import SQLiteArticleRepository
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.migration_runner import MigrationError, apply_migrations
from obs_chat_bot.data.sqlite.processing_error_repository import (
    SQLiteProcessingErrorRecorder,
)
from obs_chat_bot.presentation.telegram.bot import TelegramBotError, run_telegram_bot
from obs_chat_bot.presentation.cli.smoke import SQLiteSmokeError, run_sqlite_smoke
from obs_chat_bot.presentation.cli.smoke import PipelineSmokeError, run_pipeline_smoke

ProcessArticleUrlUseCaseFactory = Callable[
    [sqlite3.Connection],
    ProcessArticleUrlUseCase,
]


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
    mode.add_argument(
        "--pipeline-smoke",
        action="store_true",
        help="Run article pipeline smoke scenario without network, then exit.",
    )
    mode.add_argument(
        "--process-url",
        metavar="URL",
        help="Run article pipeline for one URL, then exit.",
    )
    mode.add_argument(
        "--telegram-bot",
        action="store_true",
        help="Start Telegram bot polling.",
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

    if args.pipeline_smoke:
        return run_pipeline_smoke_command(logger)

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

    if args.process_url:
        return run_process_url_command(
            database_path=config.database_path,
            source_url=args.process_url,
            logger=logger,
        )

    if args.telegram_bot:
        return run_telegram_bot_command(
            database_path=config.database_path,
            token=config.telegram_bot_token,
            logger=logger,
        )

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


def run_pipeline_smoke_command(logger: logging.Logger) -> int:
    """Запускает smoke-сценарий article pipeline как команду приложения.

    Args:
        logger: Logger для результата проверки.

    Returns:
        Ноль при успехе, иначе единицу.
    """
    try:
        run_pipeline_smoke()
    except PipelineSmokeError as error:
        logger.error("%s", error)
        return 1

    logger.info("Pipeline smoke scenario passed")
    return 0


def run_process_url_command(
    *,
    database_path: Path,
    source_url: str,
    logger: logging.Logger,
    use_case_factory: ProcessArticleUrlUseCaseFactory | None = None,
) -> int:
    """Запускает article pipeline для одного URL из CLI.

    Args:
        database_path: Путь к рабочему файлу SQLite.
        source_url: URL статьи для обработки.
        logger: Logger для результата проверки.
        use_case_factory: Factory use case, полезная для тестов CLI без сети.

    Returns:
        Ноль при успешной обработке, иначе единицу.
    """
    try:
        factory = use_case_factory or create_process_article_url_use_case
        with connect_database(database_path) as connection:
            apply_migrations(connection)
            use_case = factory(connection)
            result = use_case.execute(ProcessArticleUrlCommand(source_url=source_url))
    except (MigrationError, OSError, sqlite3.Error) as error:
        logger.error("Could not prepare article pipeline: %s", error)
        return 1
    except ProcessArticleUrlError as error:
        logger.error("Article pipeline failed: %s", error)
        return 1

    article = result.article
    logger.info("Article pipeline passed")
    logger.info("Article id: %s", article.id)
    logger.info("Article status: %s", article.status.value)
    logger.info("Article created: %s", result.created)
    logger.info("Article extracted: %s", result.extracted)
    logger.info("Article title: %s", article.title or "missing")
    logger.info(
        "Article cleaned text length: %s",
        len(article.cleaned_text or ""),
    )

    return 0


def create_process_article_url_use_case(
    connection: sqlite3.Connection,
) -> ProcessArticleUrlUseCase:
    """Собирает concrete dependencies для обработки URL статьи.

    Args:
        connection: Открытое соединение SQLite.

    Returns:
        Use case с SQLite, HTTP и trafilatura-реализациями ports.
    """
    return ProcessArticleUrlUseCase(
        article_repository=SQLiteArticleRepository(connection),
        html_fetcher=UrllibArticleHtmlFetcher(),
        text_extractor=TrafilaturaArticleTextExtractor(),
        error_recorder=SQLiteProcessingErrorRecorder(connection),
    )


def run_telegram_bot_command(
    *,
    database_path: Path,
    token: str,
    logger: logging.Logger,
    use_case_factory: ProcessArticleUrlUseCaseFactory | None = None,
) -> int:
    """Запускает Telegram adapter как CLI-команду.

    Args:
        database_path: Путь к рабочему файлу SQLite.
        token: Telegram Bot API token.
        logger: Logger для результата запуска.
        use_case_factory: Factory use case, полезная для тестов без polling.

    Returns:
        Ноль при штатной остановке, иначе единицу.
    """
    try:
        factory = use_case_factory or create_process_article_url_use_case
        with connect_database(database_path) as connection:
            apply_migrations(connection)
            use_case = factory(connection)
            run_telegram_bot(
                token=token,
                article_url_use_case=use_case,
                logger=logger,
            )
    except KeyboardInterrupt:
        logger.info("Telegram bot stopped")
        return 0
    except (MigrationError, OSError, sqlite3.Error) as error:
        logger.error("Could not prepare Telegram bot: %s", error)
        return 1
    except TelegramBotError as error:
        logger.error("%s", error)
        return 1

    return 0
