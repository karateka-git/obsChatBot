from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


_WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]]+)\]\]")
_HEADING_PATTERN = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_INLINE_TAG_PATTERN = re.compile(r"(?<![\w/])#([\w/-]+)", re.UNICODE)


@dataclass(frozen=True, slots=True)
class MarkdownMetadata:
    """Содержит извлечённые из Obsidian Markdown метаданные."""

    title: str
    frontmatter: str | None
    tags: tuple[str, ...]
    wikilinks: tuple[str, ...]


def parse_markdown(path: str, markdown: str) -> MarkdownMetadata:
    """Извлекает title, frontmatter, tags и wikilinks из Markdown-заметки.

    Args:
        path: Относительный путь заметки внутри vault.
        markdown: Полный исходный Markdown.

    Returns:
        Нормализованные metadata для локального поиска.
    """
    frontmatter, body = _split_frontmatter(markdown)
    fields = _parse_frontmatter_fields(frontmatter)
    title = fields.get("title") or _first_heading(body)
    if not title:
        title = PurePosixPath(path).stem
    frontmatter_tags = _parse_tags(fields.get("tags"))
    inline_tags = tuple(match.group(1) for match in _INLINE_TAG_PATTERN.finditer(body))
    wikilinks = tuple(
        _normalize_wikilink(match.group(1))
        for match in _WIKILINK_PATTERN.finditer(body)
    )
    return MarkdownMetadata(
        title=title,
        frontmatter=frontmatter,
        tags=_ordered_unique((*frontmatter_tags, *inline_tags)),
        wikilinks=_ordered_unique(value for value in wikilinks if value),
    )


def _split_frontmatter(markdown: str) -> tuple[str | None, str]:
    lines = markdown.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, markdown
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[1:index]).rstrip("\r\n"), "".join(lines[index + 1 :])
    return None, markdown


def _parse_frontmatter_fields(frontmatter: str | None) -> dict[str, str]:
    if frontmatter is None:
        return {}
    fields: dict[str, str] = {}
    lines = frontmatter.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if ":" not in line or line[:1].isspace():
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip().casefold()
        value = value.strip().strip("\"'")
        if key == "tags" and not value:
            items: list[str] = []
            index += 1
            while index < len(lines):
                candidate = lines[index].strip()
                if not candidate.startswith("-"):
                    break
                items.append(candidate[1:].strip().strip("\"'"))
                index += 1
            fields[key] = ",".join(items)
            continue
        fields[key] = value
        index += 1
    return fields


def _parse_tags(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    cleaned = value.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    return tuple(
        tag
        for item in cleaned.split(",")
        if (tag := item.strip().strip("\"'").removeprefix("#"))
    )


def _first_heading(markdown: str) -> str | None:
    match = _HEADING_PATTERN.search(markdown)
    return match.group(1).strip() if match else None


def _normalize_wikilink(value: str) -> str:
    target = value.split("|", 1)[0].split("#", 1)[0]
    return target.strip()


def _ordered_unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
