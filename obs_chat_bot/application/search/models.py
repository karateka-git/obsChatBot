"""Application-модели chunks до сохранения в project storage."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class VaultNoteChunkDraft:
    """Связывает универсальный chunk с сохранённой заметкой пользователя."""

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


@dataclass(frozen=True, slots=True)
class ChunkIndexUpdate:
    """Содержит счётчики одной операции обновления chunk index."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0

    def __post_init__(self) -> None:
        if min(self.created, self.updated, self.deleted, self.unchanged) < 0:
            raise ValueError("chunk index counters must not be negative")

    @property
    def processed(self) -> int:
        """Возвращает число chunks в новом наборе без удалённых записей."""
        return self.created + self.updated + self.unchanged

    def merge(self, other: ChunkIndexUpdate) -> ChunkIndexUpdate:
        """Объединяет независимые счётчики последовательных операций."""
        return ChunkIndexUpdate(
            created=self.created + other.created,
            updated=self.updated + other.updated,
            deleted=self.deleted + other.deleted,
            unchanged=self.unchanged + other.unchanged,
        )


@dataclass(frozen=True, slots=True)
class VaultChunkEmbeddingDraft:
    """Содержит новый float-вектор chunk до записи в project storage."""

    app_user_id: int
    vault_id: int
    chunk_id: int
    document_model: str
    content_hash: str
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if min(self.app_user_id, self.vault_id, self.chunk_id) <= 0:
            raise ValueError("embedding IDs must be positive")
        if not self.document_model.strip():
            raise ValueError("document_model must not be empty")
        if not self.content_hash.strip():
            raise ValueError("content_hash must not be empty")
        if not self.values:
            raise ValueError("values must not be empty")
        if any(not isfinite(value) for value in self.values):
            raise ValueError("values must contain only finite numbers")

    @property
    def dimension(self) -> int:
        """Возвращает размерность сохраняемого вектора."""
        return len(self.values)


@dataclass(frozen=True, slots=True)
class EmbeddingIndexUpdate:
    """Содержит счётчики обновления embedding-индекса vault."""

    embedded: int = 0
    deleted: int = 0
    unchanged: int = 0
    dimension: int | None = None

    def __post_init__(self) -> None:
        if min(self.embedded, self.deleted, self.unchanged) < 0:
            raise ValueError("embedding index counters must not be negative")
        if self.dimension is not None and self.dimension <= 0:
            raise ValueError("dimension must be positive when present")
