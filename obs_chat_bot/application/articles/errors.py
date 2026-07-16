from __future__ import annotations


class ArticleFetchError(RuntimeError):
    """Ошибка загрузки HTML страницы статьи."""


class ArticleExtractionError(RuntimeError):
    """Ошибка извлечения чистого текста статьи из HTML."""
