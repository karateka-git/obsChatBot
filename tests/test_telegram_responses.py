"""Тесты форматирования ответов Telegram adapter."""

from dataclasses import replace
import unittest

from obs_chat_bot.application.articles.analysis import AnalyzeArticleResult
from obs_chat_bot.application.articles.processing import ProcessArticleUrlResult
from obs_chat_bot.domain.articles.analysis import ArticleAnalysisResult
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus
from obs_chat_bot.presentation.telegram.responses import (
    format_article_analysis_result,
    format_article_processing_result,
)


class TelegramResponsesTest(unittest.TestCase):
    """Проверяет пользовательский текст по результату обработки статьи."""

    def test_format_article_processing_result_reports_created_article(self) -> None:
        """Новая статья получает понятный текст с названием, статусом, ID и длиной."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=_article(),
                created=True,
                extracted=True,
            )
        )

        self.assertIn("Готово: статья сохранена.", reply)
        self.assertIn("Название: Article title", reply)
        self.assertIn("Статус: текст извлечен", reply)
        self.assertIn("ID статьи: 1", reply)
        self.assertIn("Текст: 11 символов", reply)

    def test_format_article_processing_result_reports_existing_article(self) -> None:
        """Повторная ссылка получает отдельный текст без намека на новую запись."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=_article(),
                created=False,
                extracted=False,
            )
        )

        self.assertIn("Эта статья уже была сохранена.", reply)

    def test_format_article_processing_result_reports_updated_article(self) -> None:
        """Повторно извлеченная статья получает текст обновления."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=_article(),
                created=False,
                extracted=True,
            )
        )

        self.assertIn("Готово: статья обновлена.", reply)

    def test_format_article_processing_result_uses_fallbacks(self) -> None:
        """Ответ остается понятным, если у статьи нет заголовка или ID."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=replace(_article(), id=None, title=None, cleaned_text=None),
                created=True,
                extracted=False,
            )
        )

        self.assertIn("Название: без заголовка", reply)
        self.assertIn("ID статьи: не сохранен", reply)
        self.assertIn("Текст: 0 символов", reply)

    def test_format_article_analysis_result_includes_markdown_analysis(self) -> None:
        """Ответ с анализом содержит служебный контекст и Markdown LLM."""
        processing_result = ProcessArticleUrlResult(
            article=_article(),
            created=True,
            extracted=True,
        )
        analysis_result = AnalyzeArticleResult(
            article=replace(_article(), status=ArticleStatus.ANALYZED),
            analysis=ArticleAnalysisResult(
                id=1,
                article_id=1,
                llm_model="fake-llm",
                prompt_version="article-summary-v1",
                result_text="## Кратко\nГотовый анализ.",
            ),
            created=True,
        )

        reply = format_article_analysis_result(processing_result, analysis_result)

        self.assertIn("Готово: статья сохранена.", reply)
        self.assertIn("Анализ готов.", reply)
        self.assertIn("## Кратко", reply)


def _article() -> Article:
    """Создает минимальную статью для тестов Telegram-ответов."""
    return Article(
        id=1,
        source_url="https://example.com/article",
        normalized_url="https://example.com/article",
        title="Article title",
        cleaned_text="Clean text.",
        status=ArticleStatus.EXTRACTED,
    )


if __name__ == "__main__":
    unittest.main()
