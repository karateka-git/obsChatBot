"""Тесты SQLite-записи ошибок обработки статей."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.articles.stages import ProcessingStage
from obs_chat_bot.data.sqlite.article_repository import SQLiteArticleRepository
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.incoming_message_repository import (
    SQLiteIncomingMessageRepository,
)
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
                    incoming_message_id=None,
                    stage=ProcessingStage.FETCHING,
                    error_type="ArticleFetchError",
                    error_message="offline",
                )

                row = connection.execute(
                    """
                    SELECT
                        article_id,
                        incoming_message_id,
                        stage,
                        error_type,
                        error_message
                    FROM processing_errors
                    """
                ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["article_id"], article.id)
        self.assertIsNone(row["incoming_message_id"])
        self.assertEqual(row["stage"], "fetching")
        self.assertEqual(row["error_type"], "ArticleFetchError")
        self.assertEqual(row["error_message"], "offline")

    def test_record_links_error_to_incoming_message(self) -> None:
        """Recorder сохраняет связь ошибки с входящим сообщением."""
        with TemporaryDirectory(prefix="obs-chat-bot-errors-") as temporary_directory:
            database_path = Path(temporary_directory) / "test.db"

            with connect_database(database_path) as connection:
                apply_migrations(connection)
                incoming_message = SQLiteIncomingMessageRepository(connection).save(
                    IncomingMessage(
                        channel="telegram",
                        chat_id="100",
                        message_id="200",
                        text="https://example.com/article",
                    )
                )
                recorder = SQLiteProcessingErrorRecorder(connection)

                recorder.record(
                    article_id=None,
                    incoming_message_id=incoming_message.id,
                    stage=ProcessingStage.NORMALIZATION,
                    error_type="ValueError",
                    error_message="bad url",
                )

                row = connection.execute(
                    """
                    SELECT incoming_message_id, stage, error_type, error_message
                    FROM processing_errors
                    """
                ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["incoming_message_id"], incoming_message.id)
        self.assertEqual(row["stage"], "normalization")
        self.assertEqual(row["error_type"], "ValueError")
        self.assertEqual(row["error_message"], "bad url")


if __name__ == "__main__":
    unittest.main()
