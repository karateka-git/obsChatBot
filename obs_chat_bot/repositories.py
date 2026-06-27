"""Репозитории для сохранения и чтения моделей приложения."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .models import Article, ArticleStatus


ARTICLE_COLUMNS = """
    id,
    source_url,
    normalized_url,
    title,
    cleaned_text,
    text_hash,
    status,
    created_at,
    updated_at
"""


class ArticleRepositoryError(RuntimeError):
    """Базовая ошибка операций `ArticleRepository`."""


class ArticleAlreadyExistsError(ArticleRepositoryError):
    """Ошибка создания статьи с уже сохранённым нормализованным URL."""

    def __init__(self, article: Article) -> None:
        """Создаёт ошибку и сохраняет найденную статью.

        Args:
            article: Существующая статья с тем же нормализованным URL.
        """
        self.article = article
        super().__init__(
            f"Article already exists for normalized URL: {article.normalized_url}"
        )


class ArticleRepository:
    """Изолирует SQL-операции с таблицей `articles`.

    Args:
        connection: Соединение SQLite, созданное через `connect_database`.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, article: Article) -> Article:
        """Сохраняет новую статью и возвращает модель с ID и timestamps.

        Args:
            article: Несохранённая статья без ID.

        Returns:
            Статья, прочитанная из базы после вставки.

        Raises:
            ValueError: Если переданная статья уже содержит ID.
            ArticleAlreadyExistsError: Если нормализованный URL уже сохранён.
            ArticleRepositoryError: Если созданную запись не удалось прочитать.
        """
        if article.id is not None:
            raise ValueError("A new article must not have an id")

        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO articles (
                        source_url,
                        normalized_url,
                        title,
                        cleaned_text,
                        text_hash,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.source_url,
                        article.normalized_url,
                        article.title,
                        article.cleaned_text,
                        article.text_hash,
                        article.status.value,
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.find_by_normalized_url(article.normalized_url)
            if existing is not None:
                raise ArticleAlreadyExistsError(existing) from None
            raise

        article_id = cursor.lastrowid
        if article_id is None:
            raise ArticleRepositoryError("SQLite did not return a new article id")

        created = self.get_by_id(article_id)
        if created is None:
            raise ArticleRepositoryError(
                f"Created article could not be read: {article_id}"
            )
        return created

    def get_by_id(self, article_id: int) -> Article | None:
        """Возвращает статью по ID.

        Args:
            article_id: Идентификатор статьи в SQLite.

        Returns:
            Найденная статья или `None`, если такого ID нет.
        """
        row = self._connection.execute(
            f"SELECT {ARTICLE_COLUMNS} FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        return _row_to_article(row) if row is not None else None

    def find_by_normalized_url(self, normalized_url: str) -> Article | None:
        """Ищет статью по нормализованному URL.

        Args:
            normalized_url: URL в канонической форме.

        Returns:
            Найденная статья или `None`.

        Raises:
            ValueError: Если передан пустой URL.
        """
        if not normalized_url.strip():
            raise ValueError("normalized_url must not be empty")

        row = self._connection.execute(
            f"SELECT {ARTICLE_COLUMNS} FROM articles WHERE normalized_url = ?",
            (normalized_url,),
        ).fetchone()
        return _row_to_article(row) if row is not None else None

    def find_by_text_hash(self, text_hash: str) -> list[Article]:
        """Возвращает все статьи с одинаковым хешем очищенного текста.

        Args:
            text_hash: Хеш очищенного текста статьи.

        Returns:
            Список статей по возрастанию ID.

        Raises:
            ValueError: Если передан пустой хеш.
        """
        if not text_hash.strip():
            raise ValueError("text_hash must not be empty")

        rows = self._connection.execute(
            f"""
            SELECT {ARTICLE_COLUMNS}
            FROM articles
            WHERE text_hash = ?
            ORDER BY id
            """,
            (text_hash,),
        ).fetchall()
        return [_row_to_article(row) for row in rows]

    def update_status(
        self,
        article_id: int,
        status: ArticleStatus,
    ) -> Article | None:
        """Обновляет статус статьи.

        Args:
            article_id: Идентификатор статьи.
            status: Новый статус обработки.

        Returns:
            Обновлённая статья или `None`, если статья не найдена.
        """
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE articles
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status.value, article_id),
            )

        return self.get_by_id(article_id) if cursor.rowcount else None

    def update_content(
        self,
        article_id: int,
        *,
        title: str | None,
        cleaned_text: str,
        text_hash: str,
        status: ArticleStatus = ArticleStatus.EXTRACTED,
    ) -> Article | None:
        """Сохраняет извлечённое содержимое и новый статус статьи.

        Args:
            article_id: Идентификатор статьи.
            title: Заголовок страницы, если он найден.
            cleaned_text: Очищенный текст статьи.
            text_hash: Хеш очищенного текста.
            status: Статус после сохранения содержимого.

        Returns:
            Обновлённая статья или `None`, если статья не найдена.

        Raises:
            ValueError: Если текст или его хеш пусты.
        """
        if not cleaned_text.strip():
            raise ValueError("cleaned_text must not be empty")
        if not text_hash.strip():
            raise ValueError("text_hash must not be empty")

        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE articles
                SET
                    title = ?,
                    cleaned_text = ?,
                    text_hash = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    title,
                    cleaned_text,
                    text_hash,
                    status.value,
                    article_id,
                ),
            )

        return self.get_by_id(article_id) if cursor.rowcount else None


def _row_to_article(row: sqlite3.Row) -> Article:
    """Преобразует строку SQLite во внутреннюю модель статьи."""
    return Article(
        id=row["id"],
        source_url=row["source_url"],
        normalized_url=row["normalized_url"],
        title=row["title"],
        cleaned_text=row["cleaned_text"],
        text_hash=row["text_hash"],
        status=ArticleStatus(row["status"]),
        created_at=_parse_utc_timestamp(row["created_at"]),
        updated_at=_parse_utc_timestamp(row["updated_at"]),
    )


def _parse_utc_timestamp(value: str) -> datetime:
    """Преобразует SQLite timestamp в timezone-aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
