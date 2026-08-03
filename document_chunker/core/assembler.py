"""Общий assembler структурных блоков в ограниченные по размеру chunks."""

from __future__ import annotations

from collections.abc import Iterable
import re

from document_chunker.core.hashing import build_chunk_key, build_content_hash
from document_chunker.core.models import (
    BlockKind,
    DocumentBlock,
    DocumentChunk,
    SourceDocument,
)
from document_chunker.core.policy import ChunkingPolicy


_SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?…])\s+")


class ChunkAssembler:
    """Собирает format-neutral blocks в детерминированные chunks."""

    def __init__(self, policy: ChunkingPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> ChunkingPolicy:
        """Возвращает неизменяемую policy текущего assembler."""
        return self._policy

    def assemble(
        self,
        *,
        document: SourceDocument,
        blocks: tuple[DocumentBlock, ...],
    ) -> tuple[DocumentChunk, ...]:
        """Преобразует упорядоченные blocks в итоговые chunks.

        Args:
            document: Исходный документ для metadata и content hash.
            blocks: Результат format-specific parser.

        Returns:
            Chunks в порядке документа. Пустой набор blocks даёт пустой результат.
        """
        chunks: list[DocumentChunk] = []
        for section_blocks in _group_sections(blocks):
            texts = self._assemble_section(section_blocks)
            first_block = section_blocks[0]
            for part_index, text in enumerate(texts):
                chunks.append(
                    DocumentChunk(
                        position=len(chunks),
                        heading_path=first_block.heading_path,
                        part_index=part_index,
                        text=text,
                        chunk_key=build_chunk_key(
                            section_key=first_block.section_key,
                            part_index=part_index,
                        ),
                        content_hash=build_content_hash(
                            document=document,
                            heading_path=first_block.heading_path,
                            text=text,
                        ),
                    )
                )
        return tuple(chunks)

    def _assemble_section(
        self,
        blocks: tuple[DocumentBlock, ...],
    ) -> tuple[str, ...]:
        pieces: list[str] = []
        for block in blocks:
            pieces.extend(self._split_block(block))

        chunks: list[str] = []
        current = ""
        for piece in pieces:
            if not current:
                current = piece
                continue
            candidate = f"{current}\n\n{piece}"
            if len(candidate) <= self._policy.target_size_chars:
                current = candidate
                continue
            if (
                len(current) < self._policy.minimum_size_chars
                and len(candidate) <= self._policy.maximum_size_chars
            ):
                current = candidate
                continue
            chunks.append(current)
            current = piece
        if current:
            chunks.append(current)
        return tuple(chunks)

    def _split_block(self, block: DocumentBlock) -> tuple[str, ...]:
        text = block.text.strip()
        if len(text) <= self._policy.maximum_size_chars or not block.splittable:
            return (text,)
        if block.kind in {BlockKind.LIST, BlockKind.QUOTE}:
            units = tuple(line for line in text.splitlines() if line.strip())
            return _pack_units(
                units,
                separator="\n",
                maximum_size=self._policy.maximum_size_chars,
            )
        sentences = tuple(
            sentence.strip()
            for sentence in _SENTENCE_BOUNDARY_PATTERN.split(text)
            if sentence.strip()
        )
        return _pack_units(
            sentences,
            separator=" ",
            maximum_size=self._policy.maximum_size_chars,
        )


def _group_sections(
    blocks: tuple[DocumentBlock, ...],
) -> tuple[tuple[DocumentBlock, ...], ...]:
    groups: list[tuple[DocumentBlock, ...]] = []
    current: list[DocumentBlock] = []
    current_key: str | None = None
    for block in blocks:
        if current_key is not None and block.section_key != current_key:
            groups.append(tuple(current))
            current = []
        current.append(block)
        current_key = block.section_key
    if current:
        groups.append(tuple(current))
    return tuple(groups)


def _pack_units(
    units: Iterable[str],
    *,
    separator: str,
    maximum_size: int,
) -> tuple[str, ...]:
    packed: list[str] = []
    current = ""
    for unit in units:
        for safe_unit in _split_oversized_unit(unit, maximum_size=maximum_size):
            candidate = safe_unit if not current else f"{current}{separator}{safe_unit}"
            if len(candidate) <= maximum_size:
                current = candidate
                continue
            if current:
                packed.append(current)
            current = safe_unit
    if current:
        packed.append(current)
    return tuple(packed)


def _split_oversized_unit(unit: str, *, maximum_size: int) -> tuple[str, ...]:
    cleaned = unit.strip()
    if len(cleaned) <= maximum_size:
        return (cleaned,)

    words = cleaned.split()
    if len(words) > 1:
        return _pack_units(words, separator=" ", maximum_size=maximum_size)

    # Строка без доступных границ всё равно не должна нарушить hard limit.
    return tuple(
        cleaned[start : start + maximum_size]
        for start in range(0, len(cleaned), maximum_size)
    )
