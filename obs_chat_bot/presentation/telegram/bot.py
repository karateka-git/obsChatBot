from __future__ import annotations

import asyncio
import logging
from typing import Any

from obs_chat_bot.application.articles.incoming_messages import (
    IncomingMessage,
    SavedIncomingMessage,
)
from obs_chat_bot.application.articles.analysis import (
    AnalyzeArticleCommand,
    AnalyzeArticleError,
    AnalyzeArticleUseCase,
)
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlError,
    ProcessArticleUrlUseCase,
)
from obs_chat_bot.application.articles.ports import IncomingMessageRepository
from obs_chat_bot.application.articles.url_extraction import extract_first_supported_url
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
    logger: logging.Logger,
) -> None:
    """Запускает Telegram-бота в polling-режиме.

    Args:
        token: Telegram Bot API token.
        article_url_use_case: Use case обработки найденной ссылки.
        article_analysis_use_case: Optional use case LLM-анализа статьи.
        incoming_message_repository: Optional port сохранения входящих сообщений.
        logger: Logger для сообщений adapter.

    Raises:
        TelegramBotError: Если `aiogram` недоступен или polling завершился ошибкой.
    """
    try:
        asyncio.run(
            _run_telegram_bot(
                token=token,
                article_url_use_case=article_url_use_case,
                article_analysis_use_case=article_analysis_use_case,
                incoming_message_repository=incoming_message_repository,
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
    logger: logging.Logger,
) -> None:
    """Регистрирует минимальные handlers Telegram adapter."""
    router = aiogram.Router()

    @router.message(aiogram.filters.Command("start"))
    async def handle_start(message: Any) -> None:
        """Отвечает на стартовую команду Telegram-бота."""
        await message.answer("obsChatBot запущен. Отправь ссылку на статью.")

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
    logger: logging.Logger,
) -> str:
    """Обрабатывает входящее сообщение Telegram adapter.

    Args:
        incoming_message: Сообщение в application-формате.
        article_url_use_case: Use case обработки найденного URL.
        article_analysis_use_case: Optional use case LLM-анализа статьи.
        incoming_message_repository: Optional port сохранения сообщения со ссылкой.
        logger: Logger для диагностических сообщений.

    Returns:
        Текст ответа пользователю.
    """
    url = extract_first_supported_url(incoming_message.text)
    if url is None:
        return "Пришли ссылку на статью, и я попробую её сохранить."

    saved_message: SavedIncomingMessage | None = None
    if incoming_message_repository is not None:
        saved_message = incoming_message_repository.save(incoming_message)

    try:
        result = article_url_use_case.execute(
            ProcessArticleUrlCommand(
                source_url=url,
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
                incoming_message_id=(
                    saved_message.id if saved_message is not None else None
                ),
            )
        )
    except AnalyzeArticleError as error:
        logger.error("Telegram article analysis failed: %s", error)
        return (
            "Статью удалось сохранить, но анализ пока не получился. "
            "Я сохранил ошибку для диагностики."
        )

    return format_article_analysis_result(result, analysis_result)


def _format_processing_error(error: ProcessArticleUrlError) -> str:
    """Формирует понятный ответ пользователю по ошибке article pipeline."""
    message = str(error)
    if "normalize" in message:
        return "Не удалось разобрать ссылку. Проверь URL и пришли его ещё раз."
    if "fetch" in message:
        return (
            "Не удалось загрузить страницу по ссылке. "
            "Я сохранил ошибку для диагностики."
        )
    if "extract" in message:
        return (
            "Страница загрузилась, но текст статьи извлечь не получилось. "
            "Я сохранил ошибку для диагностики."
        )
    return "Не удалось обработать ссылку. Я сохранил ошибку для диагностики."


def _incoming_message_from_telegram(message: Any) -> IncomingMessage:
    """Преобразует Telegram message в application-модель."""
    return IncomingMessage(
        channel="telegram",
        chat_id=str(message.chat.id),
        message_id=str(message.message_id),
        text=message.text or "",
    )


def _load_aiogram() -> Any:
    """Загружает `aiogram` только при реальном запуске Telegram adapter."""
    try:
        import aiogram
        import aiogram.filters
    except ModuleNotFoundError as error:
        raise TelegramBotError("aiogram is not installed") from error

    return aiogram
