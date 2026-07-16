from __future__ import annotations

import asyncio
import logging
from typing import Any

from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlError,
    ProcessArticleUrlResult,
    ProcessArticleUrlUseCase,
)
from obs_chat_bot.application.articles.url_extraction import extract_first_supported_url


class TelegramBotError(RuntimeError):
    """Ошибка запуска Telegram adapter."""


def run_telegram_bot(
    *,
    token: str,
    article_url_use_case: ProcessArticleUrlUseCase,
    logger: logging.Logger,
) -> None:
    """Запускает Telegram-бота в polling-режиме.

    Args:
        token: Telegram Bot API token.
        article_url_use_case: Use case обработки найденной ссылки.
        logger: Logger для сообщений adapter.

    Raises:
        TelegramBotError: Если `aiogram` недоступен или polling завершился ошибкой.
    """
    try:
        asyncio.run(
            _run_telegram_bot(
                token=token,
                article_url_use_case=article_url_use_case,
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
            logger=logger,
        )
        await message.answer(reply)

    dispatcher.include_router(router)


def process_incoming_message(
    incoming_message: IncomingMessage,
    *,
    article_url_use_case: ProcessArticleUrlUseCase,
    logger: logging.Logger,
) -> str:
    """Обрабатывает входящее сообщение Telegram adapter.

    Args:
        incoming_message: Сообщение в application-формате.
        article_url_use_case: Use case обработки найденного URL.
        logger: Logger для диагностических сообщений.

    Returns:
        Текст ответа пользователю.
    """
    url = extract_first_supported_url(incoming_message.text)
    if url is None:
        return "Пришли ссылку на статью, и я попробую её сохранить."

    try:
        result = article_url_use_case.execute(ProcessArticleUrlCommand(source_url=url))
    except ProcessArticleUrlError as error:
        logger.error("Telegram article processing failed: %s", error)
        return "Не удалось обработать ссылку. Я сохранил ошибку для диагностики."

    return _format_article_result(result)


def _incoming_message_from_telegram(message: Any) -> IncomingMessage:
    """Преобразует Telegram message в application-модель."""
    return IncomingMessage(
        channel="telegram",
        chat_id=str(message.chat.id),
        message_id=str(message.message_id),
        text=message.text or "",
    )


def _format_article_result(result: ProcessArticleUrlResult) -> str:
    """Формирует короткий ответ Telegram-пользователю."""
    article = result.article
    title = article.title or "без заголовка"
    text_length = len(article.cleaned_text or "")

    if result.created:
        prefix = "Статья сохранена"
    elif result.extracted:
        prefix = "Статья обновлена"
    else:
        prefix = "Эта статья уже была сохранена"

    return (
        f"{prefix}: {title}\n"
        f"Статус: {article.status.value}\n"
        f"Длина текста: {text_length}"
    )


def _load_aiogram() -> Any:
    """Загружает `aiogram` только при реальном запуске Telegram adapter."""
    try:
        import aiogram
        import aiogram.filters
    except ModuleNotFoundError as error:
        raise TelegramBotError("aiogram is not installed") from error

    return aiogram
