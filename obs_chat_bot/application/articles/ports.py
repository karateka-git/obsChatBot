from __future__ import annotations

from typing import Protocol

from obs_chat_bot.application.articles.extracted import ExtractedArticle
from obs_chat_bot.application.articles.html import ArticleHtml
from obs_chat_bot.application.articles.incoming_messages import (
    IncomingMessage,
    SavedIncomingMessage,
)
from obs_chat_bot.application.articles.stages import ProcessingStage
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus


class ArticleRepository(Protocol):
    """Описывает операции хранения статей, нужные application-слою."""

    def create(self, article: Article) -> Article:
        """Сохраняет новую статью.

        Args:
            article: Доменная модель статьи без ID.

        Returns:
            Сохранённая доменная модель статьи.
        """

    def get_by_id(self, article_id: int) -> Article | None:
        """Возвращает статью по ID или `None`, если записи нет."""

    def find_by_normalized_url(self, normalized_url: str) -> Article | None:
        """Ищет статью по нормализованному URL."""

    def find_by_text_hash(self, text_hash: str) -> list[Article]:
        """Возвращает статьи с одинаковым хешем очищенного текста."""

    def update_status(
        self,
        article_id: int,
        status: ArticleStatus,
    ) -> Article | None:
        """Обновляет статус статьи."""

    def update_content(
        self,
        article_id: int,
        *,
        title: str | None,
        cleaned_text: str,
        text_hash: str,
        status: ArticleStatus = ArticleStatus.EXTRACTED,
    ) -> Article | None:
        """Сохраняет извлечённый контент статьи."""


class ArticleHtmlFetcher(Protocol):
    """Описывает загрузчик HTML страницы статьи."""

    def fetch(self, url: str) -> ArticleHtml:
        """Загружает HTML по URL.

        Args:
            url: Поддерживаемый URL статьи.

        Returns:
            HTML страницы вместе с исходным и финальным URL.

        Raises:
            ArticleFetchError: Если страницу не удалось загрузить.
        """


class ArticleTextExtractor(Protocol):
    """Описывает извлечение чистого текста статьи из HTML."""

    def extract(self, html: ArticleHtml) -> ExtractedArticle:
        """Извлекает содержательный текст статьи.

        Args:
            html: HTML страницы статьи.

        Returns:
            Очищенный текст статьи и найденные метаданные.

        Raises:
            ArticleExtractionError: Если текст статьи извлечь не удалось.
        """


class ProcessingErrorRecorder(Protocol):
    """Описывает запись диагностических ошибок обработки статьи."""

    def record(
        self,
        *,
        article_id: int | None,
        stage: ProcessingStage,
        error_type: str,
        error_message: str,
    ) -> None:
        """Сохраняет информацию об ошибке pipeline.

        Args:
            article_id: ID статьи, если она уже была создана.
            stage: Этап обработки, на котором произошла ошибка.
            error_type: Имя класса ошибки.
            error_message: Текст ошибки.
        """


class IncomingMessageRepository(Protocol):
    """Описывает хранение входящих сообщений из внешних каналов."""

    def save(self, message: IncomingMessage) -> SavedIncomingMessage:
        """Сохраняет входящее сообщение или возвращает уже существующую запись.

        Args:
            message: Нормализованное сообщение из presentation-слоя.

        Returns:
            Сохранённое сообщение с ID записи.
        """

    def link_to_article(
        self,
        *,
        incoming_message_id: int,
        article_id: int,
    ) -> SavedIncomingMessage | None:
        """Привязывает сохранённое входящее сообщение к статье.

        Args:
            incoming_message_id: ID сохранённого входящего сообщения.
            article_id: ID статьи, созданной или найденной после обработки URL.

        Returns:
            Обновлённое сообщение или `None`, если запись не найдена.
        """
