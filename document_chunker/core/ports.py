"""Ports синтаксических parsers независимой библиотеки."""

from __future__ import annotations

from typing import Protocol

from document_chunker.core.models import DocumentBlock, DocumentFormat, SourceDocument


class DocumentParser(Protocol):
    """Описывает parser одного явно выбранного формата документа."""

    @property
    def format(self) -> DocumentFormat:
        """Возвращает формат, поддерживаемый parser."""

    @property
    def version(self) -> str:
        """Возвращает версию поведения parser для index signature."""

    def parse(self, document: SourceDocument) -> tuple[DocumentBlock, ...]:
        """Преобразует документ в упорядоченные структурные блоки.

        Args:
            document: Документ поддерживаемого формата.

        Returns:
            Структурные блоки в порядке исходного документа.

        Raises:
            ValueError: Если передан документ другого формата.
        """
