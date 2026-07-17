from __future__ import annotations

from obs_chat_bot.application.articles.analysis import AnalyzeArticleResult
from obs_chat_bot.application.articles.processing import ProcessArticleUrlResult
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageResult,
)
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


def format_incoming_message_result(result: ProcessIncomingMessageResult) -> str:
    """Формирует Telegram-ответ по структурированному результату общего flow."""
    match result.type:
        case IncomingMessageResultType.UNKNOWN_IDENTITY:
            return _format_unknown_identity_response()
        case IncomingMessageResultType.REGISTERED:
            return "Готово, я зарегистрировал тебя. Теперь пришли ссылку на статью."
        case IncomingMessageResultType.LINK_CODE_CREATED:
            if result.link_code is None:
                return "Не удалось создать код привязки. Попробуй позже."
            return (
                f"Код привязки: `{result.link_code.code}`\n"
                f"Открой другой канал и отправь: `/link {result.link_code.code}`\n"
                "Код действует 10 минут."
            )
        case IncomingMessageResultType.LINK_COMMAND_INVALID:
            return "Пришли команду в формате `/link <код>`."
        case IncomingMessageResultType.LINKED:
            return "Готово, я привязал этот канал к твоему пользователю."
        case IncomingMessageResultType.LINK_ALREADY_BOUND:
            return "Этот канал уже привязан к пользователю."
        case IncomingMessageResultType.LINK_CODE_INVALID:
            return "Код привязки не найден или уже истек. Создай новый через `/link_code`."
        case IncomingMessageResultType.ARTICLE_URL_MISSING:
            return "Пришли ссылку на статью, и я попробую ее сохранить."
        case IncomingMessageResultType.ARTICLE_PROCESSED:
            if result.article_result is None:
                return "Статья обработана, но результат не удалось подготовить."
            return format_article_processing_result(result.article_result)
        case IncomingMessageResultType.ARTICLE_ANALYZED:
            if result.article_result is None or result.analysis_result is None:
                return "Анализ готов, но результат не удалось подготовить."
            return format_article_analysis_result(
                result.article_result,
                result.analysis_result,
            )
        case IncomingMessageResultType.ARTICLE_PROCESSING_FAILED:
            return _format_processing_error(result.error)
        case IncomingMessageResultType.ARTICLE_ANALYSIS_FAILED:
            return (
                "Статью удалось сохранить, но анализ пока не получился. "
                "Попробуй отправить ссылку позже."
            )


def _article_action_text(result: ProcessArticleUrlResult) -> str:
    """Выбирает первую строку ответа по тому, что сделал pipeline."""
    if result.created:
        return "Готово: статья сохранена."
    if result.extracted:
        return "Готово: статья обновлена."
    return "Эта статья уже была сохранена."


def _format_unknown_identity_response() -> str:
    """Возвращает подсказку для первого входа из нового канала."""
    return (
        "Я пока не знаю этот канал.\n"
        "Отправь `/register`, чтобы создать нового пользователя, или `/link <код>`, "
        "чтобы привязать этот канал к уже существующему пользователю."
    )


def _format_processing_error(error: Exception | None) -> str:
    """Формирует понятный ответ пользователю по ошибке article pipeline."""
    message = str(error) if error is not None else ""
    if "normalize" in message:
        return "Не удалось разобрать ссылку. Проверь URL и пришли его еще раз."
    if "fetch" in message:
        return "Не удалось загрузить страницу по ссылке. Попробуй отправить ее позже."
    if "extract" in message:
        return "Страница загрузилась, но текст статьи извлечь не получилось."
    return "Не удалось обработать ссылку. Попробуй отправить ее позже."
