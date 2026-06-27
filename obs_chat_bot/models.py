from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArticleStatus(StrEnum):
    """Описывает этап обработки сохранённой статьи."""

    # Запись создана, обработка ещё не началась.
    NEW = "new"
    # Страница загружается по исходному URL.
    FETCHING = "fetching"
    # Чистый текст извлечён из загруженной страницы.
    EXTRACTED = "extracted"
    # Извлечённый текст обрабатывается LLM.
    ANALYZING = "analyzing"
    # Результат LLM-анализа сохранён.
    ANALYZED = "analyzed"
    # Статья ожидает сопоставления с заметками Obsidian.
    NEEDS_OBSIDIAN_REVIEW = "needs_obsidian_review"
    # Проверка и сопоставление с Obsidian завершены.
    REVIEWED = "reviewed"
    # Обработка остановлена из-за ошибки на одном из этапов.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Article:
    """Представляет статью независимо от способа её хранения."""

    source_url: str
    normalized_url: str
    id: int | None = None
    title: str | None = None
    cleaned_text: str | None = None
    text_hash: str | None = None
    status: ArticleStatus = ArticleStatus.NEW
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source_url.strip():
            raise ValueError("source_url must not be empty")
        if not self.normalized_url.strip():
            raise ValueError("normalized_url must not be empty")
        if not isinstance(self.status, ArticleStatus):
            raise TypeError("status must be an ArticleStatus")
