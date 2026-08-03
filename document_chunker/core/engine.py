"""Публичный engine выбора parser и сборки chunks."""

from __future__ import annotations

from hashlib import sha256
import json
from types import MappingProxyType
from typing import Mapping

from document_chunker.core.assembler import ChunkAssembler
from document_chunker.core.models import DocumentChunk, DocumentFormat, SourceDocument
from document_chunker.core.policy import ChunkingPolicy
from document_chunker.core.ports import DocumentParser


# Меняется при несовместимом изменении общего assembler или структуры keys.
DOCUMENT_CHUNKER_VERSION = "1"


class UnsupportedDocumentFormatError(ValueError):
    """Сообщает, что engine не получил parser требуемого формата."""


class DocumentChunker:
    """Координирует format-specific parser и общий chunk assembler.

    Args:
        parsers: Реализации parsers по явно поддерживаемым форматам.
        policy: Настройки размеров chunks.

    Raises:
        ValueError: Если parsers отсутствуют либо зарегистрированы некорректно.
    """

    def __init__(
        self,
        *,
        parsers: Mapping[DocumentFormat, DocumentParser],
        policy: ChunkingPolicy | None = None,
    ) -> None:
        copied_parsers = dict(parsers)
        if not copied_parsers:
            raise ValueError("at least one document parser is required")
        for document_format, parser in copied_parsers.items():
            if not isinstance(document_format, DocumentFormat):
                raise TypeError("parser keys must be DocumentFormat values")
            if parser.format is not document_format:
                raise ValueError("parser format does not match registry key")
            if not parser.version.strip():
                raise ValueError("parser version must not be empty")
        self._parsers = MappingProxyType(copied_parsers)
        self._assembler = ChunkAssembler(policy or ChunkingPolicy())

    @property
    def policy(self) -> ChunkingPolicy:
        """Возвращает фактическую policy engine."""
        return self._assembler.policy

    def split(self, document: SourceDocument) -> tuple[DocumentChunk, ...]:
        """Разбивает один документ parser его явного формата.

        Args:
            document: Универсальный исходный документ.

        Returns:
            Детерминированные chunks в порядке документа.

        Raises:
            UnsupportedDocumentFormatError: Если parser формата не зарегистрирован.
        """
        parser = self._parsers.get(document.format)
        if parser is None:
            raise UnsupportedDocumentFormatError(
                f"document format is not supported: {document.format.value}"
            )
        blocks = parser.parse(document)
        return self._assembler.assemble(document=document, blocks=blocks)

    def signature_for(self, document_format: DocumentFormat) -> str:
        """Возвращает signature алгоритма, parser и policy для формата.

        Args:
            document_format: Формат будущего или существующего индекса.

        Returns:
            Стабильный SHA-256 signature.

        Raises:
            UnsupportedDocumentFormatError: Если parser формата не зарегистрирован.
        """
        parser = self._parsers.get(document_format)
        if parser is None:
            raise UnsupportedDocumentFormatError(
                f"document format is not supported: {document_format.value}"
            )
        payload = json.dumps(
            {
                "document_chunker_version": DOCUMENT_CHUNKER_VERSION,
                "format": document_format.value,
                "parser_version": parser.version,
                "policy_signature": self.policy.signature,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()
