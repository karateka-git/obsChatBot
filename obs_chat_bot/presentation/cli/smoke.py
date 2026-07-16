"""Smoke-сценарии для быстрой проверки основных контуров приложения."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from obs_chat_bot.application.articles.extracted import ExtractedArticle
from obs_chat_bot.application.articles.html import ArticleHtml
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlUseCase,
)
from obs_chat_bot.data.sqlite.article_repository import (
    ArticleRepositoryError,
    SQLiteArticleRepository,
)
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.migration_runner import MigrationError, apply_migrations
from obs_chat_bot.data.sqlite.processing_error_repository import (
    SQLiteProcessingErrorRecorder,
)
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus


class SQLiteSmokeError(RuntimeError):
    """Ошибка прохождения smoke-сценария SQLite."""


class PipelineSmokeError(RuntimeError):
    """Ошибка прохождения smoke-сценария article pipeline."""


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


def run_pipeline_smoke() -> None:
    """Проверяет article pipeline на fake HTML без сети и `trafilatura`.

    Raises:
        PipelineSmokeError: Если pipeline не сохранил статью, не извлёк текст
            или повторно обработал уже сохранённый URL.
    """
    try:
        with TemporaryDirectory(prefix="obs-chat-bot-pipeline-smoke-") as temporary_directory:
            database_path = Path(temporary_directory) / "pipeline-smoke.db"
            _run_pipeline_scenario(database_path)
    except (
        MigrationError,
        ArticleRepositoryError,
        OSError,
        sqlite3.Error,
        ValueError,
    ) as error:
        raise PipelineSmokeError(f"Pipeline smoke scenario failed: {error}") from error


def _run_sqlite_scenario(database_path: Path) -> None:
    """Выполняет проверки SQLite на указанном временном файле."""
    with connect_database(database_path) as connection:
        first_run = apply_migrations(connection)
        if not first_run:
            raise SQLiteSmokeError("Fresh database did not receive migrations")

        second_run = apply_migrations(connection)
        if second_run:
            raise SQLiteSmokeError("Migrations were applied more than once")

        repository = SQLiteArticleRepository(connection)
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


def _run_pipeline_scenario(database_path: Path) -> None:
    """Выполняет article pipeline на временной базе и fake зависимостях."""
    with connect_database(database_path) as connection:
        apply_migrations(connection)

        repository = SQLiteArticleRepository(connection)
        fetcher = _FakeArticleHtmlFetcher()
        extractor = _FakeArticleTextExtractor()
        use_case = ProcessArticleUrlUseCase(
            article_repository=repository,
            html_fetcher=fetcher,
            text_extractor=extractor,
            error_recorder=SQLiteProcessingErrorRecorder(connection),
        )

        first_result = use_case.execute(
            ProcessArticleUrlCommand(
                source_url="https://example.com/article?utm_source=smoke"
            )
        )

        if not first_result.created:
            raise PipelineSmokeError("Pipeline did not create a new article")
        if not first_result.extracted:
            raise PipelineSmokeError("Pipeline did not extract article text")
        if first_result.article.status != ArticleStatus.EXTRACTED:
            raise PipelineSmokeError("Pipeline did not mark article as extracted")
        if first_result.article.normalized_url != "https://example.com/article":
            raise PipelineSmokeError("Pipeline did not normalize article URL")
        if first_result.article.cleaned_text != _FakeArticleTextExtractor.CLEANED_TEXT:
            raise PipelineSmokeError("Pipeline saved unexpected cleaned text")

        second_result = use_case.execute(
            ProcessArticleUrlCommand(source_url="https://example.com/article")
        )

        if second_result.created:
            raise PipelineSmokeError("Pipeline created duplicate article")
        if second_result.extracted:
            raise PipelineSmokeError("Pipeline re-extracted already processed article")
        if fetcher.calls != ["https://example.com/article?utm_source=smoke"]:
            raise PipelineSmokeError("Pipeline fetched HTML unexpected number of times")


class _FakeArticleHtmlFetcher:
    """Fake HTML-загрузчик для smoke-проверки pipeline."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> ArticleHtml:
        """Возвращает стабильный HTML без сетевого запроса."""
        self.calls.append(url)
        return ArticleHtml(
            source_url=url,
            final_url="https://example.com/article",
            content="<html><body><article>Smoke article</article></body></html>",
            content_type="text/html",
        )


class _FakeArticleTextExtractor:
    """Fake extractor для smoke-проверки pipeline."""

    CLEANED_TEXT = "Smoke article text"

    def extract(self, html: ArticleHtml) -> ExtractedArticle:
        """Возвращает стабильный очищенный текст без `trafilatura`."""
        return ExtractedArticle(
            source_url=html.source_url,
            final_url=html.final_url,
            title="Smoke article",
            cleaned_text=self.CLEANED_TEXT,
        )
