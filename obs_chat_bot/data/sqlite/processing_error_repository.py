from __future__ import annotations

import sqlite3

from obs_chat_bot.application.articles.stages import ProcessingStage
from obs_chat_bot.data.sqlite.processing_error_dtos import ProcessingErrorDto


class SQLiteProcessingErrorRecorder:
    """Сохраняет диагностические ошибки article pipeline в SQLite.

    Args:
        connection: Соединение SQLite, созданное через `connect_database`.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record(
        self,
        *,
        article_id: int | None,
        stage: ProcessingStage,
        error_type: str,
        error_message: str,
    ) -> None:
        """Сохраняет ошибку обработки статьи.

        Args:
            article_id: ID статьи, если она уже была создана.
            stage: Этап обработки, на котором произошла ошибка.
            error_type: Имя класса ошибки.
            error_message: Текст ошибки.
        """
        dto = ProcessingErrorDto(
            article_id=article_id,
            stage=stage.value,
            error_type=error_type,
            error_message=error_message,
        )

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO processing_errors (
                    article_id,
                    incoming_message_id,
                    stage,
                    error_type,
                    error_message
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    dto.article_id,
                    dto.incoming_message_id,
                    dto.stage,
                    dto.error_type,
                    dto.error_message,
                ),
            )
