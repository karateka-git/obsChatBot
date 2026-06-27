"""Smoke-сценарии для быстрой проверки основных контуров приложения."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from .database import connect_database
from .migration_runner import MigrationError, apply_migrations
from .models import Article
from .repositories import ArticleRepository, ArticleRepositoryError


class SQLiteSmokeError(RuntimeError):
    """Ошибка прохождения smoke-сценария SQLite."""


def run_sqlite_smoke() -> None:
    """Проверяет миграции и `ArticleRepository` на временной базе.

    Raises:
        SQLiteSmokeError: Если миграции или чтение сохранённой статьи не работают.
    """
    try:
        with TemporaryDirectory(prefix="obs-chat-bot-smoke-") as temporary_directory:
            database_path = Path(temporary_directory) / "smoke.db"
            _run_sqlite_scenario(database_path)
    except (MigrationError, ArticleRepositoryError, OSError, sqlite3.Error) as error:
        raise SQLiteSmokeError(f"SQLite smoke scenario failed: {error}") from error


def _run_sqlite_scenario(database_path: Path) -> None:
    """Выполняет проверки SQLite на указанном временном файле."""
    with connect_database(database_path) as connection:
        first_run = apply_migrations(connection)
        if not first_run:
            raise SQLiteSmokeError("Fresh database did not receive migrations")

        second_run = apply_migrations(connection)
        if second_run:
            raise SQLiteSmokeError("Migrations were applied more than once")

        repository = ArticleRepository(connection)
        expected = Article(
            source_url="https://example.com/article?utm_source=smoke",
            normalized_url="https://example.com/article",
        )
        created = repository.create(expected)

        if created.id is None:
            raise SQLiteSmokeError("Created article does not have an id")

        loaded = repository.get_by_id(created.id)
        if loaded != created:
            raise SQLiteSmokeError("Loaded article differs from the created article")

        found = repository.find_by_normalized_url(expected.normalized_url)
        if found != created:
            raise SQLiteSmokeError("Article was not found by normalized URL")
