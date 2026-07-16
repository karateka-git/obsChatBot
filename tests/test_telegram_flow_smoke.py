"""Smoke-тест Telegram-only MVP без реального Telegram и LLM."""

from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from obs_chat_bot.application.articles.analysis import AnalyzeArticleUseCase
from obs_chat_bot.application.articles.extracted import ExtractedArticle
from obs_chat_bot.application.articles.html import ArticleHtml
from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.articles.processing import ProcessArticleUrlUseCase
from obs_chat_bot.data.sqlite.analysis_result_repository import (
    SQLiteArticleAnalysisResultRepository,
)
from obs_chat_bot.data.sqlite.article_repository import SQLiteArticleRepository
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.incoming_message_repository import (
    SQLiteIncomingMessageRepository,
)
from obs_chat_bot.data.sqlite.migration_runner import apply_migrations
from obs_chat_bot.data.sqlite.processing_error_repository import (
    SQLiteProcessingErrorRecorder,
)
from obs_chat_bot.domain.articles.analysis import ArticleAnalysisResult
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.presentation.telegram.bot import process_incoming_message


class SilentLogger:
    """Logger-заглушка для smoke-теста Telegram-flow."""

    def error(self, *_args: object, **_kwargs: object) -> None:
        """Игнорирует error-сообщение."""


class TelegramFlowSmokeTest(unittest.TestCase):
    """Проверяет ежедневный Telegram-сценарий на временной SQLite-базе."""

    def test_telegram_flow_saves_message_article_and_analysis(self) -> None:
        """Ссылка проходит весь MVP-flow и повторно использует сохранённые данные."""
        with TemporaryDirectory(prefix="obs-chat-bot-telegram-flow-") as directory:
            database_path = Path(directory) / "telegram-flow.db"
            with connect_database(database_path) as connection:
                apply_migrations(connection)
                fetcher = FakeArticleHtmlFetcher()
                analyzer = FakeArticleAnalyzer()
                article_repository = SQLiteArticleRepository(connection)
                process_use_case = ProcessArticleUrlUseCase(
                    article_repository=article_repository,
                    html_fetcher=fetcher,
                    text_extractor=FakeArticleTextExtractor(),
                    error_recorder=SQLiteProcessingErrorRecorder(connection),
                )
                analysis_use_case = AnalyzeArticleUseCase(
                    article_repository=article_repository,
                    analyzer=analyzer,
                    analysis_result_repository=SQLiteArticleAnalysisResultRepository(
                        connection
                    ),
                    error_recorder=SQLiteProcessingErrorRecorder(connection),
                )
                message_repository = SQLiteIncomingMessageRepository(connection)

                first_reply = process_incoming_message(
                    _message("10"),
                    article_url_use_case=process_use_case,
                    article_analysis_use_case=analysis_use_case,
                    incoming_message_repository=message_repository,
                    logger=SilentLogger(),
                )
                second_reply = process_incoming_message(
                    _message("11"),
                    article_url_use_case=process_use_case,
                    article_analysis_use_case=analysis_use_case,
                    incoming_message_repository=message_repository,
                    logger=SilentLogger(),
                )

                counts = _read_counts(connection)

        self.assertIn("Анализ готов.", first_reply)
        self.assertIn("## Кратко", first_reply)
        self.assertIn("Использую сохраненный анализ.", second_reply)
        self.assertEqual(fetcher.calls, ["https://example.com/article?utm_source=tg"])
        self.assertEqual(analyzer.article_ids, [1])
        self.assertEqual(counts["articles"], 1)
        self.assertEqual(counts["incoming_messages"], 2)
        self.assertEqual(counts["analysis_results"], 1)
        self.assertEqual(counts["processing_errors"], 0)


class FakeArticleHtmlFetcher:
    """Fake HTML-загрузчик для Telegram-flow smoke."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> ArticleHtml:
        """Возвращает стабильный HTML без сетевого запроса."""
        self.calls.append(url)
        return ArticleHtml(
            source_url=url,
            final_url="https://example.com/article",
            content="<html><body><article>Telegram smoke</article></body></html>",
            content_type="text/html",
        )


class FakeArticleTextExtractor:
    """Fake extractor для Telegram-flow smoke."""

    def extract(self, html: ArticleHtml) -> ExtractedArticle:
        """Возвращает очищенный текст без вызова `trafilatura`."""
        return ExtractedArticle(
            source_url=html.source_url,
            final_url=html.final_url,
            title="Telegram smoke article",
            cleaned_text="Telegram smoke article text",
        )


class FakeArticleAnalyzer:
    """Fake LLM-анализатор для Telegram-flow smoke."""

    def __init__(self) -> None:
        self.article_ids: list[int] = []

    def analyze(self, article: Article) -> ArticleAnalysisResult:
        """Возвращает стабильный Markdown-анализ без LLM-запроса."""
        if article.id is None:
            raise ValueError("article must contain id")
        self.article_ids.append(article.id)
        return ArticleAnalysisResult(
            article_id=article.id,
            llm_model="fake-llm",
            prompt_version="article-summary-v1",
            result_text="## Кратко\nTelegram smoke analysis.",
        )


def _message(message_id: str) -> IncomingMessage:
    """Создаёт входящее Telegram-сообщение со ссылкой."""
    return IncomingMessage(
        channel="telegram",
        chat_id="100",
        message_id=message_id,
        text="https://example.com/article?utm_source=tg",
    )


def _read_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Считает записи MVP-таблиц после smoke-сценария."""
    tables = [
        "articles",
        "incoming_messages",
        "analysis_results",
        "processing_errors",
    ]
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }


if __name__ == "__main__":
    unittest.main()
