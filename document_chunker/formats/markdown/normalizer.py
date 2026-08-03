"""Нормализация Markdown-текста и структурных заголовков."""

from __future__ import annotations

from pathlib import PurePosixPath
import re


_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_newlines(text: str) -> str:
    """Приводит CRLF/CR к единому LF без изменения остального текста."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_heading(heading: str) -> str:
    """Нормализует пробелы заголовка для стабильного structural key."""
    return _WHITESPACE_PATTERN.sub(" ", heading).strip().casefold()


def fallback_title(source_name: str | None) -> str | None:
    """Возвращает имя источника без расширения как fallback title."""
    if source_name is None:
        return None
    normalized = source_name.replace("\\", "/")
    title = PurePosixPath(normalized).stem.strip()
    return title or None
