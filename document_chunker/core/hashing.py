"""Детерминированные keys и hashes результата chunking."""

from __future__ import annotations

from hashlib import sha256
import json

from document_chunker.core.models import SourceDocument


def build_chunk_key(*, section_key: str, part_index: int) -> str:
    """Строит компактный стабильный ключ части структурного раздела."""
    payload = json.dumps(
        [section_key, part_index],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def build_content_hash(
    *,
    document: SourceDocument,
    heading_path: tuple[str, ...],
    text: str,
) -> str:
    """Хеширует фактический индексируемый контекст одного chunk.

    В hash включены metadata и структурный путь: их изменение должно обновить
    будущий embedding даже при неизменном тексте раздела.
    """
    payload = json.dumps(
        {
            "format": document.format.value,
            "heading_path": heading_path,
            "metadata": sorted(document.metadata.items()),
            "source_name": document.source_name,
            "text": text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()
