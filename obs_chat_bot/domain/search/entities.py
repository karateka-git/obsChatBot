"""Доменные сущности chunks и состояния поискового индекса."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True, slots=True)
class VaultNoteChunk:
    """Представляет сохранённый структурный fragment Markdown-заметки."""

    app_user_id: int
    vault_id: int
    note_id: int
    note_path: str
    chunk_key: str
    position: int
    heading_path: tuple[str, ...]
    part_index: int
    text: str
    content_hash: str
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.app_user_id <= 0:
            raise ValueError("app_user_id must be positive")
        if self.vault_id <= 0:
            raise ValueError("vault_id must be positive")
        if self.note_id <= 0:
            raise ValueError("note_id must be positive")
        if not self.note_path.strip():
            raise ValueError("note_path must not be empty")
        if not self.chunk_key.strip():
            raise ValueError("chunk_key must not be empty")
        if self.position < 0:
            raise ValueError("position must not be negative")
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("heading_path must not contain empty values")
        if self.part_index < 0:
            raise ValueError("part_index must not be negative")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if not self.content_hash.strip():
            raise ValueError("content_hash must not be empty")
        if self.id is not None and self.id <= 0:
            raise ValueError("id must be positive")


@dataclass(frozen=True, slots=True)
class VaultChunkIndexState:
    """Фиксирует signature полностью согласованного индекса одного vault."""

    app_user_id: int
    vault_id: int
    index_signature: str
    indexed_at: datetime

    def __post_init__(self) -> None:
        if self.app_user_id <= 0:
            raise ValueError("app_user_id must be positive")
        if self.vault_id <= 0:
            raise ValueError("vault_id must be positive")
        if not self.index_signature.strip():
            raise ValueError("index_signature must not be empty")


@dataclass(frozen=True, slots=True)
class VaultChunkSearchHit:
    """Представляет chunk, найденный полнотекстовым поиском.

    Attributes:
        chunk: Сохранённый chunk, доступный текущему пользователю и vault.
        score: Релевантность результата; большее значение означает более
            высокую позицию в выдаче.
    """

    chunk: VaultNoteChunk
    score: float

    def __post_init__(self) -> None:
        if not isfinite(self.score) or self.score < 0:
            raise ValueError("score must be finite and not negative")


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """Представляет числовой semantic-вектор, возвращённый одной моделью.

    Attributes:
        model: Стабильный ID embedding-модели провайдера.
        values: Конечные float-координаты непустого вектора.
    """

    model: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not self.values:
            raise ValueError("values must not be empty")
        if any(not isfinite(value) for value in self.values):
            raise ValueError("values must contain only finite numbers")

    @property
    def dimension(self) -> int:
        """Возвращает число координат вектора."""
        return len(self.values)
