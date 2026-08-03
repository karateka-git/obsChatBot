"""Тесты независимого document chunker и Markdown/Obsidian parser."""

from __future__ import annotations

import unittest

from document_chunker import (
    BlockKind,
    ChunkingPolicy,
    DocumentChunker,
    DocumentFormat,
    MarkdownDocumentParser,
    SourceDocument,
    UnsupportedDocumentFormatError,
)


class DocumentChunkerTest(unittest.TestCase):
    """Проверяет детерминированное структурное разбиение документов."""

    def test_splits_markdown_by_nested_headings_and_ignores_frontmatter(self) -> None:
        """Каждый непустой раздел получает полный heading path без YAML."""
        chunks = _engine().split(
            SourceDocument(
                text="""---
tags: [github, auth]
---
# GitHub App
Общее описание.

## Device Flow
Пользователь вводит код.

### Проверка
Приложение проверяет авторизацию.
""",
                format=DocumentFormat.MARKDOWN,
                source_name="GitHub App.md",
                metadata={"title": "GitHub App", "tags": "github, auth"},
            )
        )

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].heading_path, ("GitHub App",))
        self.assertEqual(chunks[1].heading_path, ("GitHub App", "Device Flow"))
        self.assertEqual(
            chunks[2].heading_path,
            ("GitHub App", "Device Flow", "Проверка"),
        )
        self.assertNotIn("tags:", "\n".join(chunk.text for chunk in chunks))

    def test_uses_source_name_for_document_without_headings(self) -> None:
        """Плоский Markdown получает fallback title из имени источника."""
        chunks = _engine().split(
            SourceDocument(
                text="Один абзац без заголовка.",
                format=DocumentFormat.MARKDOWN,
                source_name="Folder/JWT.md",
            )
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].heading_path, ("JWT",))

    def test_keeps_fenced_code_and_does_not_parse_heading_inside_it(self) -> None:
        """Markdown внутри fence остаётся code block текущего раздела."""
        document = SourceDocument(
            text="""# Python
Описание.

```python
# Это комментарий
print("ok")
```

Продолжение.
""",
            format=DocumentFormat.MARKDOWN,
        )
        parser = MarkdownDocumentParser()
        blocks = parser.parse(document)
        chunks = _engine().split(document)

        self.assertEqual([block.kind for block in blocks], [
            BlockKind.PARAGRAPH,
            BlockKind.CODE,
            BlockKind.PARAGRAPH,
        ])
        self.assertFalse(blocks[1].splittable)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].heading_path, ("Python",))
        self.assertIn("# Это комментарий", chunks[0].text)

    def test_classifies_lists_tables_and_obsidian_callouts(self) -> None:
        """Структурные Markdown-блоки сохраняют подходящий тип и границы."""
        blocks = MarkdownDocumentParser().parse(
            SourceDocument(
                text="""# Форматы
- один
- два

| A | B |
| --- | --- |
| 1 | 2 |

> [!NOTE]
> Важный callout.
""",
                format=DocumentFormat.MARKDOWN,
            )
        )

        self.assertEqual(
            [block.kind for block in blocks],
            [BlockKind.LIST, BlockKind.TABLE, BlockKind.QUOTE],
        )
        self.assertFalse(blocks[1].splittable)

    def test_duplicate_headings_have_distinct_stable_keys(self) -> None:
        """Вставка другого sibling не меняет keys повторяющихся заголовков."""
        before = _engine().split(
            SourceDocument(
                text="""# Root
Вводная.
## Example
Первый.
## Example
Второй.
""",
                format=DocumentFormat.MARKDOWN,
            )
        )
        after = _engine().split(
            SourceDocument(
                text="""# Root
Вводная.
## Other
Другой.
## Example
Первый.
## Example
Второй.
""",
                format=DocumentFormat.MARKDOWN,
            )
        )

        before_examples = [chunk for chunk in before if chunk.heading_path[-1] == "Example"]
        after_examples = [chunk for chunk in after if chunk.heading_path[-1] == "Example"]
        self.assertEqual(len({chunk.chunk_key for chunk in before_examples}), 2)
        self.assertEqual(
            [chunk.chunk_key for chunk in before_examples],
            [chunk.chunk_key for chunk in after_examples],
        )

    def test_splits_oversized_text_without_exceeding_hard_limit(self) -> None:
        """Большой обычный абзац делится по словам до maximum size."""
        engine = _engine(
            ChunkingPolicy(
                minimum_size_chars=10,
                target_size_chars=30,
                maximum_size_chars=40,
            )
        )
        chunks = engine.split(
            SourceDocument(
                text="# Большой раздел\n" + "слово " * 30,
                format=DocumentFormat.MARKDOWN,
            )
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.text) <= 40 for chunk in chunks))
        self.assertEqual(
            [chunk.part_index for chunk in chunks],
            list(range(len(chunks))),
        )

    def test_preserves_oversized_unsplittable_code_block(self) -> None:
        """Неделимый fenced code остаётся целым даже больше text hard limit."""
        engine = _engine(
            ChunkingPolicy(
                minimum_size_chars=10,
                target_size_chars=20,
                maximum_size_chars=30,
            )
        )
        chunks = engine.split(
            SourceDocument(
                text="# Код\n```text\n" + "x" * 80 + "\n```",
                format=DocumentFormat.MARKDOWN,
            )
        )

        self.assertEqual(len(chunks), 1)
        self.assertGreater(len(chunks[0].text), 30)
        self.assertIn("```text", chunks[0].text)

    def test_output_and_signature_are_deterministic(self) -> None:
        """Одинаковые input, parser и policy дают идентичный результат."""
        engine = _engine()
        document = SourceDocument(
            text="# JWT\nОписание токена.",
            format=DocumentFormat.MARKDOWN,
            metadata={"tags": "auth"},
        )

        self.assertEqual(engine.split(document), engine.split(document))
        self.assertEqual(
            engine.signature_for(DocumentFormat.MARKDOWN),
            engine.signature_for(DocumentFormat.MARKDOWN),
        )

    def test_metadata_changes_content_hash_but_not_structural_key(self) -> None:
        """Новые tags требуют embedding update без смены структурной identity."""
        first = _engine().split(
            SourceDocument(
                text="# JWT\nОписание.",
                format=DocumentFormat.MARKDOWN,
                metadata={"tags": "auth"},
            )
        )[0]
        second = _engine().split(
            SourceDocument(
                text="# JWT\nОписание.",
                format=DocumentFormat.MARKDOWN,
                metadata={"tags": "security"},
            )
        )[0]

        self.assertEqual(first.chunk_key, second.chunk_key)
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_policy_changes_index_signature(self) -> None:
        """Иное разбиение помечается другой signature будущего индекса."""
        default_signature = _engine().signature_for(DocumentFormat.MARKDOWN)
        changed_signature = _engine(
            ChunkingPolicy(
                minimum_size_chars=300,
                target_size_chars=1500,
                maximum_size_chars=3000,
            )
        ).signature_for(DocumentFormat.MARKDOWN)

        self.assertNotEqual(default_signature, changed_signature)

    def test_rejects_unregistered_document_format(self) -> None:
        """Engine не угадывает parser по тексту или расширению."""
        with self.assertRaises(UnsupportedDocumentFormatError):
            _engine().split(
                SourceDocument(
                    text="Обычный текст",
                    format=DocumentFormat.PLAIN_TEXT,
                    source_name="note.txt",
                )
            )

    def test_empty_document_has_no_chunks(self) -> None:
        """Пустой документ не создаёт фиктивную индексную запись."""
        self.assertEqual(
            _engine().split(
                SourceDocument(text="", format=DocumentFormat.MARKDOWN)
            ),
            (),
        )


def _engine(policy: ChunkingPolicy | None = None) -> DocumentChunker:
    return DocumentChunker(
        parsers={DocumentFormat.MARKDOWN: MarkdownDocumentParser()},
        policy=policy,
    )


if __name__ == "__main__":
    unittest.main()
