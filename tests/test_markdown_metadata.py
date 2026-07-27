"""Тесты извлечения metadata из Obsidian Markdown."""

import unittest

from obs_chat_bot.application.vaults.markdown import parse_markdown


class MarkdownMetadataTest(unittest.TestCase):
    """Проверяет frontmatter, tags, заголовок и wikilinks."""

    def test_extracts_frontmatter_and_obsidian_metadata(self) -> None:
        """Парсер объединяет YAML tags, inline tags и нормализует wikilinks."""
        markdown = """---
title: "Моя заметка"
tags:
  - python
  - inbox
---
# Другой заголовок

Текст #idea с [[Folder/Note|алиасом]] и [[Target#Раздел]].
"""
        result = parse_markdown("Folder/File.md", markdown)

        self.assertEqual(result.title, "Моя заметка")
        self.assertIn("title:", result.frontmatter)
        self.assertEqual(result.tags, ("python", "inbox", "idea"))
        self.assertEqual(result.wikilinks, ("Folder/Note", "Target"))

    def test_falls_back_to_heading_and_file_name(self) -> None:
        """Без frontmatter title берётся из H1, затем из имени файла."""
        self.assertEqual(parse_markdown("A.md", "# Заголовок").title, "Заголовок")
        self.assertEqual(parse_markdown("Folder/A.md", "Текст").title, "A")


if __name__ == "__main__":
    unittest.main()
