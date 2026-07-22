from __future__ import annotations

from obs_chat_bot.application.articles.analysis import AnalyzeArticleResult
from obs_chat_bot.application.articles.processing import ProcessArticleUrlResult
from obs_chat_bot.application.articles.stages import ProcessingStage
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageResult,
)
from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionCompletion,
    GitHubConnectionCompletionStatus,
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
    """Формирует человекочитаемый ответ по результату article pipeline.

    Args:
        result: Результат обработки URL статьи.

    Returns:
        Короткий текст, который можно отправить пользователю во внешний канал.
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
    """Формирует ответ с полезной LLM-сводкой статьи.

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
    """Формирует ответ по структурированному результату общего flow."""
    match result.type:
        case IncomingMessageResultType.UNKNOWN_IDENTITY:
            return _format_unknown_identity_response()
        case IncomingMessageResultType.START_UNREGISTERED:
            return (
                "obsChatBot запущен.\n"
                "Этот канал пока не зарегистрирован.\n"
                "Отправь `/register`, чтобы создать нового пользователя, или `/link <код>`, "
                "чтобы привязать этот канал к уже существующему пользователю."
            )
        case IncomingMessageResultType.START_REGISTERED:
            if result.app_user is None:
                return "obsChatBot запущен. Пришли ссылку на статью."
            return (
                "obsChatBot запущен.\n"
                f"Этот канал уже привязан к пользователю ID {result.app_user.id}.\n"
                "Можешь прислать ссылку на статью или отправить `/link_code` для привязки другого канала."
            )
        case IncomingMessageResultType.REGISTERED:
            return "Готово, я зарегистрировал тебя. Теперь пришли ссылку на статью."
        case IncomingMessageResultType.ALREADY_REGISTERED:
            if result.app_user is None:
                return "Ты уже зарегистрирован. Теперь пришли ссылку на статью."
            return (
                "Ты уже зарегистрирован.\n"
                f"ID пользователя: {result.app_user.id}\n"
                "Теперь можно прислать ссылку на статью."
            )
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
        case IncomingMessageResultType.LINK_REBIND_CONFIRMATION_REQUIRED:
            if result.app_user is None:
                return (
                    "Этот канал уже привязан к другому пользователю.\n"
                    "Чтобы перепривязать его, ответь `да`. Чтобы оставить как есть, ответь `нет`."
                )
            return (
                "Этот канал уже привязан к другому пользователю.\n"
                f"Перепривязать его к пользователю ID {result.app_user.id}?\n"
                "Ответь `да` или `нет`."
            )
        case IncomingMessageResultType.LINK_REBOUND:
            if result.app_user is None:
                return "Готово, я перепривязал этот канал."
            return (
                "Готово, я перепривязал этот канал.\n"
                f"Теперь он связан с пользователем ID {result.app_user.id}."
            )
        case IncomingMessageResultType.LINK_REBIND_CANCELLED:
            return "Ок, оставляю текущую привязку без изменений."
        case IncomingMessageResultType.LINK_REBIND_CONFIRMATION_MISSING:
            return (
                "Не нашел ожидающую перепривязку. Если хочешь привязать этот канал "
                "к другому пользователю, снова отправь `/link <код>`."
            )
        case IncomingMessageResultType.LINK_REBIND_CONFIRMATION_PENDING:
            return (
                "Я жду ответ `да` или `нет` по перепривязке канала.\n"
                "Ответь `да`, чтобы перепривязать канал, или `нет`, чтобы оставить как есть."
            )
        case IncomingMessageResultType.STATUS:
            if result.app_user is None:
                return "Бот работает, но пользователь не определен."
            return (
                "Бот работает.\n"
                f"ID пользователя: {result.app_user.id}\n"
                "Можно прислать ссылку на статью, `/link_code` или `/reanalyze <ID статьи>`."
            )
        case IncomingMessageResultType.GITHUB_CONNECT_STARTED:
            return _format_github_connect_response(result, repeated=False)
        case IncomingMessageResultType.GITHUB_CONNECT_ALREADY_PENDING:
            return _format_github_connect_response(result, repeated=True)
        case IncomingMessageResultType.GITHUB_CONNECT_PREPARING:
            return (
                "Подключение GitHub уже запускается. "
                "Повтори `/github_connect` через несколько секунд."
            )
        case IncomingMessageResultType.GITHUB_CONNECT_UNAVAILABLE:
            return "GitHub connector пока не настроен на сервере."
        case IncomingMessageResultType.GITHUB_CONNECT_FAILED:
            return "Не удалось начать подключение GitHub. Попробуй позже."
        case IncomingMessageResultType.REANALYZE_COMMAND_INVALID:
            return "Пришли команду в формате `/reanalyze <ID статьи>`."
        case IncomingMessageResultType.ARTICLE_REANALYZED:
            if result.analysis_result is None:
                return "Анализ обновлен, но результат не удалось подготовить."
            return format_reanalysis_result(result.analysis_result)
        case IncomingMessageResultType.ARTICLE_REANALYSIS_FAILED:
            return (
                "Не удалось обновить анализ статьи. Проверь ID статьи или попробуй позже."
            )
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


def _format_github_connect_response(
    result: ProcessIncomingMessageResult,
    *,
    repeated: bool,
) -> str:
    """Формирует безопасную инструкцию GitHub App + Device Flow."""
    connection = result.github_connection
    if connection is None or connection.authorization is None:
        return "Подключение GitHub запускается. Повтори команду через несколько секунд."
    prefix = (
        "Авторизация уже ожидает подтверждения."
        if repeated
        else "Начинаю подключение GitHub."
    )
    authorization = connection.authorization
    return (
        f"{prefix}\n\n"
        "1. Установи GitHub App и выбери repository с Obsidian vault:\n"
        f"{connection.installation_url}\n\n"
        "2. Открой Device Flow:\n"
        f"{authorization.verification_uri}\n\n"
        f"3. Введи одноразовый код: `{authorization.user_code}`\n\n"
        "Проверка продолжится в фоне. Временный GitHub token не сохраняется."
    )


def format_github_connection_completion(
    completion: GitHubConnectionCompletion,
) -> str:
    """Формирует итоговый ответ фонового GitHub Device Flow."""
    match completion.status:
        case GitHubConnectionCompletionStatus.CONNECTED:
            count = completion.installation_count
            return (
                "GitHub успешно подключён.\n"
                f"Доступных установок GitHub App: {count}."
            )
        case GitHubConnectionCompletionStatus.NO_INSTALLATIONS:
            return (
                "Авторизация GitHub завершена, но доступных установок App не найдено.\n"
                "Установи GitHub App на нужный repository и повтори `/github_connect`."
            )
        case GitHubConnectionCompletionStatus.DENIED:
            return "Авторизация GitHub отклонена. Для повтора отправь `/github_connect`."
        case GitHubConnectionCompletionStatus.EXPIRED:
            return (
                "Код авторизации GitHub истёк. "
                "Отправь `/github_connect`, чтобы получить новый."
            )
        case GitHubConnectionCompletionStatus.FAILED:
            return (
                "Не удалось завершить подключение GitHub. "
                "Попробуй ещё раз через `/github_connect`."
            )
    raise ValueError(f"Unsupported GitHub completion status: {completion.status}")


def format_reanalysis_result(analysis_result: AnalyzeArticleResult) -> str:
    """Формирует ответ для принудительного повторного анализа."""
    article = analysis_result.article
    title = article.title or "без заголовка"
    article_id = article.id if article.id is not None else "не сохранен"
    return (
        "Анализ обновлен.\n\n"
        f"Название: {title}\n"
        f"ID статьи: {article_id}\n\n"
        f"{analysis_result.analysis.result_text}"
    )


def _format_unknown_identity_response() -> str:
    """Возвращает подсказку для первого входа из нового канала."""
    return (
        "Я пока не знаю этот канал.\n"
        "Отправь `/register`, чтобы создать нового пользователя, или `/link <код>`, "
        "чтобы привязать этот канал к уже существующему пользователю."
    )


def _format_processing_error(error: Exception | None) -> str:
    """Формирует понятный ответ пользователю по ошибке article pipeline."""
    stage = getattr(error, "stage", None)
    if stage == ProcessingStage.NORMALIZATION:
        return "Не удалось разобрать ссылку. Проверь URL и пришли его еще раз."
    if stage == ProcessingStage.FETCHING:
        return (
            "Не удалось загрузить страницу по ссылке. "
            "Проверь, что она открывается в браузере, или попробуй позже."
        )
    if stage == ProcessingStage.EXTRACTION:
        return (
            "Страница загрузилась, но текст статьи извлечь не получилось. "
            "Можно попробовать другую ссылку на эту же публикацию."
        )
    if stage == ProcessingStage.STORAGE:
        return "Не удалось сохранить статью. Попробуй позже."
    return "Не удалось обработать ссылку. Попробуй отправить ее позже."
