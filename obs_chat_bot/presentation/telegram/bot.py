from __future__ import annotations

import asyncio
import logging
from typing import Any

from obs_chat_bot.application.articles.analysis import (
    AnalyzeArticleCommand,
    AnalyzeArticleError,
    AnalyzeArticleUseCase,
)
from obs_chat_bot.application.articles.incoming_messages import (
    IncomingMessage,
    SavedIncomingMessage,
)
from obs_chat_bot.application.articles.ports import IncomingMessageRepository
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlError,
    ProcessArticleUrlUseCase,
)
from obs_chat_bot.application.articles.url_extraction import extract_first_supported_url
from obs_chat_bot.application.users.identity import (
    IdentityAlreadyBoundError,
    InvalidLinkCodeError,
    UserIdentityService,
)
from obs_chat_bot.domain.users.entities import AppUser, IncomingIdentity
from obs_chat_bot.presentation.telegram.responses import (
    format_article_analysis_result,
    format_article_processing_result,
)


class TelegramBotError(RuntimeError):
    """Ошибка запуска Telegram adapter."""


def run_telegram_bot(
    *,
    token: str,
    article_url_use_case: ProcessArticleUrlUseCase,
    article_analysis_use_case: AnalyzeArticleUseCase | None = None,
    incoming_message_repository: IncomingMessageRepository | None = None,
    user_identity_service: UserIdentityService | None = None,
    logger: logging.Logger,
) -> None:
    """Запускает Telegram-бота в polling-режиме."""
    try:
        asyncio.run(
            _run_telegram_bot(
                token=token,
                article_url_use_case=article_url_use_case,
                article_analysis_use_case=article_analysis_use_case,
                incoming_message_repository=incoming_message_repository,
                user_identity_service=user_identity_service,
                logger=logger,
            )
        )
    except TelegramBotError:
        raise
    except Exception as error:
        raise TelegramBotError(f"Telegram bot failed: {error}") from error


async def _run_telegram_bot(
    *,
    token: str,
    article_url_use_case: ProcessArticleUrlUseCase,
    article_analysis_use_case: AnalyzeArticleUseCase | None,
    incoming_message_repository: IncomingMessageRepository | None,
    user_identity_service: UserIdentityService | None,
    logger: logging.Logger,
) -> None:
    """Асинхронно запускает polling Telegram-бота."""
    aiogram = _load_aiogram()
    bot = aiogram.Bot(token=token)
    dispatcher = aiogram.Dispatcher()

    _register_handlers(
        dispatcher,
        aiogram,
        article_url_use_case=article_url_use_case,
        article_analysis_use_case=article_analysis_use_case,
        incoming_message_repository=incoming_message_repository,
        user_identity_service=user_identity_service,
        logger=logger,
    )

    logger.info("Telegram bot polling started")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def _register_handlers(
    dispatcher: Any,
    aiogram: Any,
    *,
    article_url_use_case: ProcessArticleUrlUseCase,
    article_analysis_use_case: AnalyzeArticleUseCase | None,
    incoming_message_repository: IncomingMessageRepository | None,
    user_identity_service: UserIdentityService | None,
    logger: logging.Logger,
) -> None:
    """Регистрирует минимальные handlers Telegram adapter."""
    router = aiogram.Router()

    @router.message(aiogram.filters.Command("start"))
    async def handle_start(message: Any) -> None:
        """Отвечает на стартовую команду Telegram-бота."""
        await message.answer(
            "obsChatBot запущен.\n"
            "Отправь /register для нового пользователя или /link <код> для привязки канала."
        )

    @router.message()
    async def handle_text(message: Any) -> None:
        """Обрабатывает текстовое сообщение через article pipeline."""
        if not message.text:
            await message.answer("Пришли текстовое сообщение со ссылкой на статью.")
            return

        incoming_message = _incoming_message_from_telegram(message)
        reply = process_incoming_message(
            incoming_message,
            article_url_use_case=article_url_use_case,
            article_analysis_use_case=article_analysis_use_case,
            incoming_message_repository=incoming_message_repository,
            user_identity_service=user_identity_service,
            logger=logger,
        )
        await message.answer(reply)

    dispatcher.include_router(router)


def process_incoming_message(
    incoming_message: IncomingMessage,
    *,
    article_url_use_case: ProcessArticleUrlUseCase,
    article_analysis_use_case: AnalyzeArticleUseCase | None = None,
    incoming_message_repository: IncomingMessageRepository | None = None,
    user_identity_service: UserIdentityService | None = None,
    logger: logging.Logger,
) -> str:
    """Обрабатывает входящее сообщение Telegram adapter."""
    app_user = _resolve_app_user(incoming_message, user_identity_service)
    if isinstance(app_user, str):
        return app_user

    incoming_message = _with_app_user(incoming_message, app_user)
    url = extract_first_supported_url(incoming_message.text)
    if url is None:
        return "Пришли ссылку на статью, и я попробую ее сохранить."

    saved_message: SavedIncomingMessage | None = None
    if incoming_message_repository is not None:
        saved_message = incoming_message_repository.save(incoming_message)

    try:
        result = article_url_use_case.execute(
            ProcessArticleUrlCommand(
                source_url=url,
                app_user_id=incoming_message.app_user_id,
                incoming_message_id=(
                    saved_message.id if saved_message is not None else None
                ),
            )
        )
    except ProcessArticleUrlError as error:
        logger.error("Telegram article processing failed: %s", error)
        return _format_processing_error(error)

    if (
        incoming_message_repository is not None
        and saved_message is not None
        and result.article.id is not None
    ):
        incoming_message_repository.link_to_article(
            incoming_message_id=saved_message.id,
            article_id=result.article.id,
        )

    if article_analysis_use_case is None or result.article.id is None:
        return format_article_processing_result(result)

    try:
        analysis_result = article_analysis_use_case.execute(
            AnalyzeArticleCommand(
                article_id=result.article.id,
                app_user_id=incoming_message.app_user_id,
                incoming_message_id=(
                    saved_message.id if saved_message is not None else None
                ),
            )
        )
    except AnalyzeArticleError as error:
        logger.error("Telegram article analysis failed: %s", error)
        return (
            "Статью удалось сохранить, но анализ пока не получился. "
            "Попробуй отправить ссылку позже."
        )

    return format_article_analysis_result(result, analysis_result)


def _resolve_app_user(
    incoming_message: IncomingMessage,
    user_identity_service: UserIdentityService | None,
) -> AppUser | str:
    """Определяет пользователя приложения или возвращает onboarding-ответ."""
    if user_identity_service is None:
        return AppUser(id=incoming_message.app_user_id)

    identity = _incoming_identity_from_message(incoming_message)
    text = incoming_message.text.strip()

    if text == "/register":
        user_identity_service.register(identity)
        return "Готово, я зарегистрировал тебя. Теперь пришли ссылку на статью."

    if text == "/link_code":
        user = user_identity_service.resolve(identity)
        if user is None:
            return _format_unknown_identity_response()
        link_code = user_identity_service.create_link_code(user.id)
        return (
            f"Код привязки: `{link_code.code}`\n"
            f"Открой другой канал и отправь: `/link {link_code.code}`\n"
            "Код действует 10 минут."
        )

    if text.startswith("/link"):
        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return "Пришли команду в формате `/link <код>`."
        try:
            user_identity_service.link(code=parts[1], identity=identity)
            return "Готово, я привязал этот канал к твоему пользователю."
        except IdentityAlreadyBoundError:
            return "Этот канал уже привязан к пользователю."
        except InvalidLinkCodeError:
            return "Код привязки не найден или уже истек. Создай новый через `/link_code`."

    user = user_identity_service.resolve(identity)
    if user is None:
        return _format_unknown_identity_response()
    return user


def _incoming_identity_from_message(incoming_message: IncomingMessage) -> IncomingIdentity:
    """Преобразует входящее сообщение в identity внешнего канала."""
    external_user_id = incoming_message.external_user_id or incoming_message.chat_id
    return IncomingIdentity(
        channel=incoming_message.channel,
        external_user_id=external_user_id,
        external_chat_id=incoming_message.chat_id,
        username=incoming_message.username,
        display_name=incoming_message.display_name,
    )


def _with_app_user(incoming_message: IncomingMessage, app_user: AppUser) -> IncomingMessage:
    """Возвращает копию сообщения с ID пользователя приложения."""
    return IncomingMessage(
        channel=incoming_message.channel,
        chat_id=incoming_message.chat_id,
        message_id=incoming_message.message_id,
        text=incoming_message.text,
        app_user_id=app_user.id,
        external_user_id=incoming_message.external_user_id,
        username=incoming_message.username,
        display_name=incoming_message.display_name,
    )


def _format_unknown_identity_response() -> str:
    """Возвращает подсказку для первого входа из нового канала."""
    return (
        "Я пока не знаю этот канал.\n"
        "Отправь `/register`, чтобы создать нового пользователя, или `/link <код>`, "
        "чтобы привязать этот канал к уже существующему пользователю."
    )


def _format_processing_error(error: ProcessArticleUrlError) -> str:
    """Формирует понятный ответ пользователю по ошибке article pipeline."""
    message = str(error)
    if "normalize" in message:
        return "Не удалось разобрать ссылку. Проверь URL и пришли его еще раз."
    if "fetch" in message:
        return "Не удалось загрузить страницу по ссылке. Попробуй отправить ее позже."
    if "extract" in message:
        return "Страница загрузилась, но текст статьи извлечь не получилось."
    return "Не удалось обработать ссылку. Попробуй отправить ее позже."


def _incoming_message_from_telegram(message: Any) -> IncomingMessage:
    """Преобразует Telegram message в application-модель."""
    telegram_user = getattr(message, "from_user", None)
    display_name = None
    if telegram_user is not None:
        display_name = (
            getattr(telegram_user, "full_name", None)
            or getattr(telegram_user, "first_name", None)
        )

    return IncomingMessage(
        channel="telegram",
        chat_id=str(message.chat.id),
        message_id=str(message.message_id),
        text=message.text or "",
        external_user_id=(
            str(telegram_user.id)
            if telegram_user is not None and getattr(telegram_user, "id", None) is not None
            else None
        ),
        username=(
            getattr(telegram_user, "username", None)
            if telegram_user is not None
            else None
        ),
        display_name=display_name,
    )


def _load_aiogram() -> Any:
    """Загружает `aiogram` только при реальном запуске Telegram adapter."""
    try:
        import aiogram
        import aiogram.filters
    except ModuleNotFoundError as error:
        raise TelegramBotError("aiogram is not installed") from error

    return aiogram
