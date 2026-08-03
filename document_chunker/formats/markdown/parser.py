"""Детерминированный структурный parser Markdown/Obsidian."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from document_chunker.core.models import (
    BlockKind,
    DocumentBlock,
    DocumentFormat,
    SourceDocument,
)
from document_chunker.core.ports import DocumentParser
from document_chunker.formats.markdown.normalizer import (
    fallback_title,
    normalize_heading,
    normalize_newlines,
)


# Меняется при несовместимом изменении правил Markdown/Obsidian parsing.
MARKDOWN_PARSER_VERSION = "1"

_ATX_HEADING_PATTERN = re.compile(
    r"^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+[ \t]*)?$"
)
_FENCE_OPEN_PATTERN = re.compile(r"^ {0,3}(`{3,}|~{3,}).*$")
_LIST_PATTERN = re.compile(r"^\s*(?:[-+*]|\d+[.)])[ \t]+")
_TABLE_DELIMITER_PATTERN = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_INDENTED_CODE_PATTERN = re.compile(r"^(?: {4}|\t)")


@dataclass(frozen=True, slots=True)
class _HeadingContext:
    level: int
    path: tuple[str, ...]
    section_key: str


class MarkdownDocumentParser(DocumentParser):
    """Разбирает Markdown на blocks с Obsidian-compatible structural path."""

    @property
    def format(self) -> DocumentFormat:
        """Возвращает поддерживаемый формат Markdown."""
        return DocumentFormat.MARKDOWN

    @property
    def version(self) -> str:
        """Возвращает версию детерминированного поведения parser."""
        return MARKDOWN_PARSER_VERSION

    def parse(self, document: SourceDocument) -> tuple[DocumentBlock, ...]:
        """Преобразует Markdown в блоки, не включая frontmatter и заголовки.

        Args:
            document: Markdown-документ с необязательными metadata.

        Returns:
            Блоки разделов в исходном порядке.

        Raises:
            ValueError: Если документ объявлен не как Markdown.
        """
        if document.format is not DocumentFormat.MARKDOWN:
            raise ValueError("MarkdownDocumentParser requires markdown format")

        body = _remove_frontmatter(normalize_newlines(document.text))
        root_title = document.metadata.get("title", "").strip() or fallback_title(
            document.source_name
        )
        current_path = (root_title,) if root_title else ()
        current_section_key = "root"
        heading_stack: list[_HeadingContext] = []
        sibling_counts: dict[tuple[str, int, str], int] = {}
        blocks: list[DocumentBlock] = []
        buffered_lines: list[str] = []

        lines = body.split("\n")
        index = 0
        while index < len(lines):
            line = lines[index]
            fence_match = _FENCE_OPEN_PATTERN.match(line)
            if fence_match is not None:
                _flush_buffer(
                    blocks,
                    buffered_lines,
                    heading_path=current_path,
                    section_key=current_section_key,
                )
                fence = fence_match.group(1)
                code_lines = [line]
                index += 1
                while index < len(lines):
                    candidate = lines[index]
                    code_lines.append(candidate)
                    index += 1
                    if _is_closing_fence(candidate, fence):
                        break
                blocks.append(
                    DocumentBlock(
                        kind=BlockKind.CODE,
                        text="\n".join(code_lines).strip(),
                        heading_path=current_path,
                        section_key=current_section_key,
                        splittable=False,
                    )
                )
                continue

            heading_match = _ATX_HEADING_PATTERN.match(line)
            if heading_match is not None:
                _flush_buffer(
                    blocks,
                    buffered_lines,
                    heading_path=current_path,
                    section_key=current_section_key,
                )
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                while heading_stack and heading_stack[-1].level >= level:
                    heading_stack.pop()

                if heading_stack:
                    parent_path = heading_stack[-1].path
                    parent_key = heading_stack[-1].section_key
                elif level > 1 and root_title:
                    parent_path = (root_title,)
                    parent_key = "root"
                else:
                    parent_path = ()
                    parent_key = "root"

                normalized_title = normalize_heading(title)
                count_key = (parent_key, level, normalized_title)
                occurrence = sibling_counts.get(count_key, 0)
                sibling_counts[count_key] = occurrence + 1
                current_section_key = _build_section_key(
                    parent_key=parent_key,
                    level=level,
                    normalized_title=normalized_title,
                    occurrence=occurrence,
                )
                current_path = (*parent_path, title)
                heading_stack.append(
                    _HeadingContext(
                        level=level,
                        path=current_path,
                        section_key=current_section_key,
                    )
                )
                index += 1
                continue

            if not line.strip():
                _flush_buffer(
                    blocks,
                    buffered_lines,
                    heading_path=current_path,
                    section_key=current_section_key,
                )
            else:
                buffered_lines.append(line)
            index += 1

        _flush_buffer(
            blocks,
            buffered_lines,
            heading_path=current_path,
            section_key=current_section_key,
        )
        return tuple(blocks)


def _remove_frontmatter(markdown: str) -> str:
    lines = markdown.split("\n")
    if not lines or lines[0].strip() != "---":
        return markdown
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :])
    return markdown


def _is_closing_fence(line: str, opening_fence: str) -> bool:
    character = re.escape(opening_fence[0])
    minimum_length = len(opening_fence)
    return re.fullmatch(
        rf" {{0,3}}{character}{{{minimum_length},}}[ \t]*",
        line,
    ) is not None


def _flush_buffer(
    blocks: list[DocumentBlock],
    buffered_lines: list[str],
    *,
    heading_path: tuple[str, ...],
    section_key: str,
) -> None:
    if not buffered_lines:
        return
    text = "\n".join(buffered_lines).strip()
    buffered_lines.clear()
    if not text:
        return
    kind, splittable = _classify_block(text)
    blocks.append(
        DocumentBlock(
            kind=kind,
            text=text,
            heading_path=heading_path,
            section_key=section_key,
            splittable=splittable,
        )
    )


def _classify_block(text: str) -> tuple[BlockKind, bool]:
    lines = text.splitlines()
    if all(_INDENTED_CODE_PATTERN.match(line) for line in lines if line.strip()):
        return BlockKind.CODE, False
    if len(lines) >= 2 and _TABLE_DELIMITER_PATTERN.match(lines[1]):
        return BlockKind.TABLE, False
    if _LIST_PATTERN.match(lines[0]):
        return BlockKind.LIST, True
    if lines[0].lstrip().startswith(">"):
        return BlockKind.QUOTE, True
    return BlockKind.PARAGRAPH, True


def _build_section_key(
    *,
    parent_key: str,
    level: int,
    normalized_title: str,
    occurrence: int,
) -> str:
    title_hash = sha256(normalized_title.encode("utf-8")).hexdigest()[:16]
    return f"{parent_key}/{level}:{title_hash}:{occurrence}"
