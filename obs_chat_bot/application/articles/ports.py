from __future__ import annotations

from typing import Protocol

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
