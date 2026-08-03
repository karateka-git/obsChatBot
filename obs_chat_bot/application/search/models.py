"""Application-модели chunks до сохранения в project storage."""

from __future__ import annotations

from dataclasses import dataclass


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
