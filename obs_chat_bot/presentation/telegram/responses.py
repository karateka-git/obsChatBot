from __future__ import annotations

from obs_chat_bot.application.articles.analysis import AnalyzeArticleResult
from obs_chat_bot.application.articles.processing import ProcessArticleUrlResult
from obs_chat_bot.domain.articles.statuses import ArticleStatus


_ARTICLE_STATUS_LABELS: dict[ArticleStatus, str] = {
    ArticleStatus.NEW: "новая",
    ArticleStatus.FETCHING: "загружается",
    ArticleStatus.EXTRACTED: "текст извлечен",
    ArticleStatus.ANALYZING: "анализируется",
    ArticleStatus.ANALYZED: "проанализирована",
    ArticleStatus.NEEDS_OBSIDIAN_REVIEW: "ждет разбора для Obsidian",
    ArticleStatus.REVIEWED: "разобрана",
    ArticleStatus.FAILED: "ошибка обработки",
}


def format_article_processing_result(result: ProcessArticleUrlResult) -> str:
    """Формирует человекочитаемый Telegram-ответ по результату article pipeline.

    Args:
        result: Результат обработки URL статьи.

    Returns:
        Короткий текст, который можно отправить пользователю в Telegram.
    """
    article = result.article
    title = article.title or "без заголовка"
    text_length = len(article.cleaned_text or "")
    status = _ARTICLE_STATUS_LABELS.get(article.status, article.status.value)
    action = _article_action_text(result)
    article_id = article.id if article.id is not None else "не сохранен"

    return (
        f"{action}\n\n"
        f"Название: {title}\n"
        f"Статус: {status}\n"
        f"ID статьи: {article_id}\n"
        f"Текст: {text_length} символов"
    )


def format_article_analysis_result(
    processing_result: ProcessArticleUrlResult,
    analysis_result: AnalyzeArticleResult,
) -> str:
    """Формирует Telegram-ответ с полезной LLM-сводкой статьи.

    Args:
        processing_result: Результат обработки URL статьи.
        analysis_result: Результат LLM-анализа статьи.

    Returns:
        Markdown-текст анализа с коротким техническим контекстом.
    """
    article = analysis_result.article
    title = article.title or "без заголовка"
    article_id = article.id if article.id is not None else "не сохранен"
    analysis_action = (
        "Анализ готов." if analysis_result.created else "Использую сохраненный анализ."
    )

    return (
        f"{_article_action_text(processing_result)}\n"
        f"{analysis_action}\n\n"
        f"Название: {title}\n"
        f"ID статьи: {article_id}\n\n"
        f"{analysis_result.analysis.result_text}"
    )


def _article_action_text(result: ProcessArticleUrlResult) -> str:
    """Выбирает первую строку ответа по тому, что сделал pipeline."""
    if result.created:
        return "Готово: статья сохранена."
    if result.extracted:
        return "Готово: статья обновлена."
    return "Эта статья уже была сохранена."
