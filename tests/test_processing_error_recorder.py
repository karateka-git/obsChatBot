"""Тесты SQLite-записи ошибок обработки статей."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from obs_chat_bot.application.articles.stages import ProcessingStage
from obs_chat_bot.data.sqlite.article_repository import SQLiteArticleRepository
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.migration_runner import apply_migrations
from obs_chat_bot.data.sqlite.processing_error_repository import (
    SQLiteProcessingErrorRecorder,
)
from obs_chat_bot.domain.articles.entities import Article


class SQLiteProcessingErrorRecorderTest(unittest.TestCase):
    """Проверяет запись diagnostic errors в SQLite."""

    def test_record_saves_processing_error(self) -> None:
        """Recorder сохраняет этап, тип и текст ошибки."""
        with TemporaryDirectory(prefix="obs-chat-bot-errors-") as temporary_directory:
            database_path = Path(temporary_directory) / "test.db"

            with connect_database(database_path) as connection:
                apply_migrations(connection)
                article = SQLiteArticleRepository(connection).create(
                    Article(
                        source_url="https://example.com/article",
                        normalized_url="https://example.com/article",
                    )
                )
                recorder = SQLiteProcessingErrorRecorder(connection)

                recorder.record(
                    article_id=article.id,
                    stage=ProcessingStage.FETCHING,
                    error_type="ArticleFetchError",
                    error_message="offline",
                )

                row = connection.execute(
                    """
                    SELECT article_id, stage, error_type, error_message
                    FROM processing_errors
                    """
                ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["article_id"], article.id)
        self.assertEqual(row["stage"], "fetching")
        self.assertEqual(row["error_type"], "ArticleFetchError")
        self.assertEqual(row["error_message"], "offline")


if __name__ == "__main__":
    unittest.main()
