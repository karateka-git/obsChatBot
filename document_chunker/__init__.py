"""Независимые инструменты структурного разбиения документов."""

from document_chunker.core.engine import (
    DocumentChunker,
    UnsupportedDocumentFormatError,
)
from document_chunker.core.models import (
    BlockKind,
    DocumentBlock,
    DocumentChunk,
    DocumentFormat,
    SourceDocument,
)
from document_chunker.core.policy import ChunkingPolicy
from document_chunker.formats.markdown.parser import MarkdownDocumentParser

__all__ = (
    "BlockKind",
    "ChunkingPolicy",
    "DocumentBlock",
    "DocumentChunk",
    "DocumentChunker",
    "DocumentFormat",
    "MarkdownDocumentParser",
    "SourceDocument",
    "UnsupportedDocumentFormatError",
)
