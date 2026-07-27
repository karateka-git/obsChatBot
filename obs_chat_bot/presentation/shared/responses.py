from __future__ import annotations

from obs_chat_bot.application.articles.analysis import AnalyzeArticleResult
from obs_chat_bot.application.articles.processing import ProcessArticleUrlResult
from obs_chat_bot.application.articles.stages import ProcessingStage
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageResult,
)
from obs_chat_bot.application.incoming.commands import ChatCommand, CommandSection
from obs_chat_bot.application.vaults.github_models import GitHubConnectionCompletionStatus
from obs_chat_bot.application.vaults.vault_sync import VaultSyncStatus
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
        case IncomingMessageResultType.HELP:
            return _format_help()
        case IncomingMessageResultType.START_UNREGISTERED:
            return (
                "obsChatBot запущен.\n"
                "Этот канал пока не зарегистрирован.\n"
                "Отправь `/register`, чтобы создать нового пользователя, или `/link <код>`, "
                "чтобы привязать этот канал к уже существующему пользователю.\n"
                "Все команды: `/help`."
            )
        case IncomingMessageResultType.START_REGISTERED:
            if result.app_user is None:
                return "obsChatBot запущен. Пришли ссылку на статью."
            return (
                "obsChatBot запущен.\n"
                f"Рад тебя видеть, {_display_name(result)}.\n"
                "Можешь прислать ссылку на статью или отправить `/help`."
            )
        case IncomingMessageResultType.REGISTERED:
            return (
                "Готово, я зарегистрировал тебя.\n"
                "Как к тебе обращаться? Пришли имя или название профиля."
            )
        case IncomingMessageResultType.REGISTRATION_NAME_REQUIRED:
            return (
                "Регистрация ещё не завершена.\n"
                "Как к тебе обращаться? Пришли имя или название профиля."
            )
        case IncomingMessageResultType.REGISTRATION_NAME_SAVED:
            if result.selected_vault is not None:
                return (
                    f"Приятно познакомиться, {_display_name(result)}.\n"
                    f"{_format_selected_vault(result)}\n"
                    "Регистрация завершена — можешь присылать ссылки на статьи."
                )
            return (
                f"Приятно познакомиться, {_display_name(result)}.\n"
                "Теперь пришли ссылку на GitHub-репозиторий с Obsidian vault.\n"
                "Если vault находится во вложенной папке, добавь путь после ссылки."
            )
        case IncomingMessageResultType.NAME_COMMAND_INVALID:
            return (
                "Не получилось сохранить имя. Используй от 1 до 80 символов "
                "без ссылки или команды.\n"
                "Например: `/name Влад`."
            )
        case IncomingMessageResultType.NAME_UPDATED:
            return f"Готово. Теперь буду обращаться к тебе: {_display_name(result)}."
        case IncomingMessageResultType.CONFIRMATION_MISSING:
            return (
                "Сейчас нет действия, которое нужно подтвердить.\n"
                "Сначала пришли ссылку на другой repository или `/link <код>`."
            )
        case IncomingMessageResultType.ALREADY_REGISTERED:
            vault = _format_selected_vault(result)
            return (
                f"{_display_name(result)}, ты уже зарегистрирован.\n"
                f"{vault}\n"
                "Можешь присылать статьи. Чтобы заменить vault, пришли ссылку "
                "на другой GitHub-репозиторий."
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
                f"Перепривязать его к профилю «{_display_name(result)}»?\n"
                "Ответь `да` или `нет`."
            )
        case IncomingMessageResultType.LINK_REBOUND:
            if result.app_user is None:
                return "Готово, я перепривязал этот канал."
            return (
                "Готово, я перепривязал этот канал.\n"
                f"Теперь он связан с профилем «{_display_name(result)}»."
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
            if result.selected_vault is None:
                return (
                    "Бот работает.\n"
                    f"Профиль: {_display_name(result)}.\n"
                    "Obsidian vault ещё не подключён.\n"
                    "Пришли ссылку на GitHub-репозиторий с vault."
                )
            return (
                "Бот работает.\n"
                f"Профиль: {_display_name(result)}.\n"
                f"{_format_selected_vault(result)}\n"
                "Можно прислать ссылку на статью, `/link_code` или `/reanalyze <ID статьи>`."
            )
        case IncomingMessageResultType.GITHUB_CONNECT_STARTED:
            return _format_github_connect_response(result, repeated=False)
        case IncomingMessageResultType.GITHUB_CONNECT_ALREADY_PENDING:
            return _format_github_connect_response(result, repeated=True)
        case IncomingMessageResultType.GITHUB_CONNECT_PREPARING:
            return "Авторизация GitHub уже запускается. Подожди несколько секунд."
        case IncomingMessageResultType.GITHUB_CONNECT_IN_PROGRESS:
            return (
                "Подключение GitHub уже выполняется в другом привязанном канале. "
                "Заверши его там или дождись истечения одноразового кода."
            )
        case IncomingMessageResultType.GITHUB_CONNECT_UNAVAILABLE:
            return "GitHub connector пока не настроен на сервере."
        case IncomingMessageResultType.GITHUB_CONNECT_FAILED:
            return _format_github_failure(result)
        case IncomingMessageResultType.GITHUB_APP_REQUIRED:
            suffix = (
                f"\n\nНастроить GitHub App:\n{result.installation_url}"
                if result.installation_url
                else ""
            )
            return (
                "GitHub-аккаунт авторизован, но GitHub App пока не имеет доступа "
                "к нужному repository."
                f"{suffix}\n\n"
                "Выбери repository и разреши `Contents: read and write`, "
                "затем снова пришли его ссылку."
            )
        case IncomingMessageResultType.REGISTRATION_VAULT_REQUIRED:
            return (
                f"{_display_name(result)}, осталось подключить Obsidian vault.\n"
                "Пришли ссылку на GitHub-репозиторий "
                "с Obsidian vault."
            )
        case IncomingMessageResultType.GITHUB_VAULT_COMMAND_INVALID:
            return (
                "Пришли обычную ссылку на GitHub repository:\n"
                "`https://github.com/owner/repository`\n"
                "или `https://github.com/owner/repository vault/path`.\n"
                "Если vault находится в корне repository, путь указывать не нужно."
            )
        case IncomingMessageResultType.GITHUB_VAULT_SELECTED:
            return _format_vault_selection(
                result,
                prefix="Obsidian vault подключён.",
            )
        case IncomingMessageResultType.GITHUB_VAULT_ALREADY_SELECTED:
            return _format_vault_selection(
                result,
                prefix="Этот Obsidian vault уже подключён.",
            )
        case (
            IncomingMessageResultType
            .GITHUB_VAULT_REPLACEMENT_CONFIRMATION_REQUIRED
        ):
            vault_description = _format_vault_selection(
                result,
                prefix="Предлагается новый vault.",
            )
            return (
                f"{vault_description}\n"
                "Он заменит текущее подключение и его локальные данные.\n"
                "Продолжить? Ответь `да` или `нет`."
            )
        case IncomingMessageResultType.GITHUB_VAULT_REPLACED:
            return _format_vault_selection(
                result,
                prefix="Obsidian vault заменён.",
            )
        case IncomingMessageResultType.GITHUB_VAULT_REPLACEMENT_CANCELLED:
            return _format_vault_selection(
                result,
                prefix="Замена отменена. Текущий vault сохранён.",
            )
        case IncomingMessageResultType.GITHUB_VAULT_CONFIRMATION_MISSING:
            return (
                "Нет ожидающей замены vault. "
                "Сначала пришли ссылку на новый GitHub repository."
            )
        case IncomingMessageResultType.GITHUB_VAULT_GITHUB_REQUIRED:
            return (
                "Для продолжения регистрации необходимо авторизовать GitHub."
            )
        case IncomingMessageResultType.GITHUB_VAULT_REPOSITORY_UNAVAILABLE:
            suffix = (
                f"\n\nНастроить GitHub App:\n{result.installation_url}"
                if result.installation_url
                else ""
            )
            return (
                "GitHub App не получила доступ на чтение и запись "
                "этого repository.\n"
                "Проверь URL, добавь repository в настройках GitHub App "
                "и разреши `Contents: read and write`."
                f"{suffix}\n\n"
                "После настройки снова пришли ссылку на repository."
            )
        case IncomingMessageResultType.GITHUB_VAULT_PATH_NOT_FOUND:
            return (
                "Указанный vault path не найден или ведёт не к каталогу.\n"
                "Проверь путь относительно корня repository."
            )
        case IncomingMessageResultType.GITHUB_VAULT_FAILED:
            return "Не удалось проверить GitHub repository. Попробуй позже."
        case IncomingMessageResultType.GITHUB_SYNC_COMPLETED:
            return _format_vault_sync(result)
        case IncomingMessageResultType.GITHUB_SYNC_FAILED:
            return (
                "Не удалось синхронизировать Obsidian vault с GitHub. "
                "Локальная копия не была помечена как актуальная. Попробуй позже."
            )
        case IncomingMessageResultType.GITHUB_STATUS:
            return _format_github_status(result)
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


def _display_name(result: ProcessIncomingMessageResult) -> str:
    """Возвращает пользовательское имя без раскрытия внутреннего ID."""
    if result.app_user is None or result.app_user.display_name is None:
        return "пользователь"
    return result.app_user.display_name


def _format_selected_vault(result: ProcessIncomingMessageResult) -> str:
    """Форматирует активный vault понятным пользователю образом."""
    vault = result.selected_vault
    if vault is None:
        return "Obsidian vault ещё не подключён."
    root = f", папка: `{vault.root_path}`" if vault.root_path else ""
    return f"Подключён vault: `{vault.owner}/{vault.repository}`{root}."


def _article_action_text(result: ProcessArticleUrlResult) -> str:
    """Выбирает первую строку ответа по тому, что сделал pipeline."""
    if result.created:
        return "Готово: статья сохранена."
    if result.extracted:
        return "Готово: статья обновлена."
    return "Эта статья уже была сохранена."


def _format_help() -> str:
    """Формирует справку из единого типизированного реестра команд."""
    lines = ["Доступные команды:"]
    for section in CommandSection:
        commands = [
            command
            for command in ChatCommand
            if command.section is section
        ]
        if not commands:
            continue
        lines.extend(
            (
                "",
                f"{section.value}:",
                *(str(command) for command in commands),
            )
        )
    lines.extend(
        (
            "",
            "После `/register` пришли ссылку на GitHub repository с Obsidian vault.",
            "После настройки пришли HTTP/HTTPS-ссылку — сохранить и "
            "проанализировать статью.",
            "",
            "Ответы `да` и `нет` используются, когда бот просит подтвердить "
            "перепривязку или замену.",
        )
    )
    return "\n".join(lines)


def _format_vault_selection(
    result: ProcessIncomingMessageResult,
    *,
    prefix: str,
) -> str:
    """Формирует безопасное описание выбранного GitHub vault."""
    selection = result.vault_selection
    if selection is None:
        return prefix
    vault = selection.vault
    root_path = vault.root_path or "корень repository"
    description = (
        f"{prefix}\n"
        f"Repository: `{vault.owner}/{vault.repository}`\n"
        f"Ветка: `{vault.branch}`\n"
        f"Vault path: `{root_path}`"
    )
    if result.error is not None:
        return (
            f"{description}\n\n"
            "Первая синхронизация не завершилась. Подключение сохранено; "
            "повтори через `/github_sync`."
        )
    if result.vault_sync_result is not None:
        return f"{description}\n\n{_format_vault_sync(result)}"
    return description


def _format_vault_sync(result: ProcessIncomingMessageResult) -> str:
    """Форматирует итог первой или ручной синхронизации vault."""
    sync = result.vault_sync_result
    if sync is None:
        return "Синхронизация vault завершилась без доступной сводки."
    if sync.status is VaultSyncStatus.NO_VAULT:
        return "Obsidian vault ещё не подключён."
    if sync.status is VaultSyncStatus.IN_PROGRESS:
        return "Этот vault уже синхронизируется. Дождись завершения."
    if sync.status is VaultSyncStatus.UNCHANGED:
        return (
            "Vault проверен: изменений нет.\n"
            f"Локально заметок: {sync.total_notes}."
        )
    return (
        "Vault синхронизирован.\n"
        f"Заметок: {sync.total_notes}; скачано: {sync.downloaded_notes}; "
        f"добавлено: {sync.added_notes}; обновлено: {sync.updated_notes}; "
        f"удалено: {sync.deleted_notes}."
    )


def _format_github_status(result: ProcessIncomingMessageResult) -> str:
    """Форматирует состояние GitHub vault и локального каталога."""
    status = result.vault_status
    if status is None or status.vault is None:
        return "Obsidian vault ещё не подключён."
    vault = status.vault
    root = vault.root_path or "корень repository"
    checked = (
        vault.last_checked_at.strftime("%Y-%m-%d %H:%M UTC")
        if vault.last_checked_at is not None
        else "ещё не проверялся"
    )
    synced = (
        vault.last_synced_at.strftime("%Y-%m-%d %H:%M UTC")
        if vault.last_synced_at is not None
        else "ещё не синхронизировался"
    )
    return (
        f"Obsidian vault: `{vault.owner}/{vault.repository}`\n"
        f"Ветка: `{vault.branch}`\n"
        f"Vault path: `{root}`\n"
        f"Локально заметок: {status.note_count}\n"
        f"Последняя проверка: {checked}\n"
        f"Последняя успешная синхронизация: {synced}"
    )


def _format_github_connect_response(
    result: ProcessIncomingMessageResult,
    *,
    repeated: bool,
) -> str:
    """Формирует безопасную инструкцию Device Flow внутри регистрации."""
    connection = result.github_connection
    if connection is None or connection.authorization is None:
        return "Авторизация GitHub запускается. Подожди несколько секунд."
    prefix = (
        "Авторизация уже ожидает подтверждения."
        if repeated
        else "Для проверки repository необходимо авторизовать GitHub."
    )
    authorization = connection.authorization
    return (
        f"{prefix}\n\n"
        "1. Открой страницу авторизации:\n"
        f"{authorization.verification_uri}\n\n"
        f"2. Введи одноразовый код: `{authorization.user_code}`\n\n"
        "После авторизации бот сам продолжит подключение vault. "
        "Временный GitHub token не сохраняется."
    )


def _format_github_failure(result: ProcessIncomingMessageResult) -> str:
    """Объясняет сбой фоновой GitHub-авторизации без технических деталей."""
    completion = result.github_completion
    if completion is None:
        return "Не удалось начать авторизацию GitHub. Попробуй позже."
    if completion.status is GitHubConnectionCompletionStatus.DENIED:
        return (
            "Авторизация GitHub отклонена. "
            "Чтобы повторить, снова пришли ссылку на repository."
        )
    if completion.status is GitHubConnectionCompletionStatus.EXPIRED:
        return (
            "Код авторизации GitHub истёк. "
            "Снова пришли ссылку на repository, чтобы получить новый."
        )
    return (
        "Не удалось завершить авторизацию GitHub. "
        "Снова пришли ссылку на repository или попробуй позже."
    )


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
