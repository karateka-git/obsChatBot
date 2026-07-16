from __future__ import annotations

from enum import StrEnum


class ProcessingStage(StrEnum):
    """Описывает этап pipeline, на котором может возникнуть ошибка."""

    # Подготовка и нормализация входного URL.
    NORMALIZATION = "normalization"
    # Создание или поиск записи статьи в хранилище.
    STORAGE = "storage"
    # Загрузка HTML страницы статьи.
    FETCHING = "fetching"
    # Извлечение чистого текста из HTML.
    EXTRACTION = "extraction"
