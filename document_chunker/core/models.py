"""Универсальные модели входа, блоков и результата chunking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class DocumentFormat(StrEnum):
    """Определяет явно выбранный синтаксический формат документа."""

    MARKDOWN = "markdown"  # Markdown, включая профиль Obsidian.
    PLAIN_TEXT = "plain_text"  # Неструктурированный текст; parser пока отсутствует.
    HTML = "html"  # HTML; parser пока отсутствует.


class BlockKind(StrEnum):
    """Описывает структурный тип блока после format-specific parsing."""

    PARAGRAPH = "paragraph"  # Обычный текстовый абзац.
    LIST = "list"  # Markdown-список.
    TABLE = "table"  # Markdown-таблица.
    CODE = "code"  # Fenced или indented code block.
    QUOTE = "quote"  # Цитата либо Obsidian callout.


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Представляет независимый от приложения исходный текст документа.

    Args:
        text: Полный текст документа.
        format: Явный формат, определяющий parser.
        source_name: Необязательное имя источника для контекста и fallback title.
        metadata: Строковые metadata, которые участвуют в индексируемом контексте.
    """

    text: str
    format: DocumentFormat
    source_name: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not isinstance(self.format, DocumentFormat):
            raise TypeError("format must be a DocumentFormat")
        if self.source_name is not None and not self.source_name.strip():
            raise ValueError("source_name must not be empty")
        copied_metadata = dict(self.metadata)
        if any(not isinstance(key, str) or not key.strip() for key in copied_metadata):
            raise ValueError("metadata keys must be non-empty strings")
        if any(not isinstance(value, str) for value in copied_metadata.values()):
            raise TypeError("metadata values must be strings")
        object.__setattr__(self, "metadata", MappingProxyType(copied_metadata))


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    """Представляет один структурный блок после разбора исходного формата.

    Args:
        kind: Тип структурного блока.
        text: Исходный текст блока без окружающих пустых строк.
        heading_path: Иерархия заголовков, к которой относится блок.
        section_key: Стабильный локальный ключ раздела внутри документа.
        splittable: Разрешено ли делить чрезмерно большой блок.
    """

    kind: BlockKind
    text: str
    heading_path: tuple[str, ...]
    section_key: str
    splittable: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BlockKind):
            raise TypeError("kind must be a BlockKind")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("heading_path must not contain empty values")
        if not self.section_key.strip():
            raise ValueError("section_key must not be empty")


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """Представляет детерминированный результат разбиения одного документа."""

    position: int
    heading_path: tuple[str, ...]
    part_index: int
    text: str
    chunk_key: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("position must not be negative")
        if self.part_index < 0:
            raise ValueError("part_index must not be negative")
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("heading_path must not contain empty values")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if not self.chunk_key.strip():
            raise ValueError("chunk_key must not be empty")
        if not self.content_hash.strip():
            raise ValueError("content_hash must not be empty")
