from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from obs_chat_bot.application.articles.url_extraction import extract_first_supported_url
from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.incoming.processing import ProcessIncomingMessageResult
from obs_chat_bot.presentation.shared.responses import (
    format_incoming_message_result,
)
from obs_chat_bot.presentation.shared.safe_send import safe_send_async


TELEGRAM_SAFE_MESSAGE_LIMIT = 3900
PROCESSING_ACK_TEXT = "Принял, обрабатываю. Это может занять немного времени."
IncomingMessageProcessor = Callable[[IncomingMessage], ProcessIncomingMessageResult]


class TelegramBotError(RuntimeError):
    """Ошибка запуска Telegram adapter."""


def run_telegram_bot(
    *,
    token: str,
    incoming_message_processor: IncomingMessageProcessor,
    logger: logging.Logger,
) -> None:
    """Запускает Telegram-бота в polling-режиме."""
    try:
        asyncio.run(
            _run_telegram_bot(
                token=token,
                incoming_message_processor=incoming_message_processor,
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
    incoming_message_processor: IncomingMessageProcessor,
    logger: logging.Logger,
) -> None:
    """Асинхронно запускает polling Telegram-бота."""
    aiogram = _load_aiogram()
    bot = aiogram.Bot(token=token)
    dispatcher = aiogram.Dispatcher()

    _register_handlers(
        dispatcher,
        aiogram,
        incoming_message_processor=incoming_message_processor,
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
    incoming_message_processor: IncomingMessageProcessor,
    logger: logging.Logger,
) -> None:
    """Регистрирует минимальные handlers Telegram adapter."""
    router = aiogram.Router()

    @router.message()
    async def handle_text(message: Any) -> None:
        """Обрабатывает текстовое сообщение через article pipeline."""
        if not message.text:
            await safe_send_telegram_reply(
                message,
                "Пришли текстовое сообщение со ссылкой на статью.",
                logger=logger,
            )
            return

        incoming_message = _incoming_message_from_telegram(message)
        if _should_send_processing_ack(message.text):
            await safe_send_telegram_reply(
                message,
                PROCESSING_ACK_TEXT,
                logger=logger,
            )

        result = await asyncio.to_thread(
            incoming_message_processor,
            incoming_message,
        )
        if result.error is not None:
            logger.error("Telegram incoming message processing failed: %s", result.error)
        reply = format_incoming_message_result(result)
        await safe_send_telegram_reply(message, reply, logger=logger)

    dispatcher.include_router(router)


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


async def send_telegram_reply(
    message: Any,
    text: str,
    *,
    limit: int = TELEGRAM_SAFE_MESSAGE_LIMIT,
) -> None:
    """Отправляет длинный Telegram-ответ безопасными частями.

    Args:
        message: Aiogram message или совместимый fake в тестах.
        text: Текст ответа.
        limit: Максимальная длина одного сообщения с запасом ниже лимита Telegram.
    """
    for chunk in split_telegram_message(text, limit=limit):
        await message.answer(chunk)


async def safe_send_telegram_reply(
    message: Any,
    text: str,
    *,
    logger: logging.Logger,
    limit: int = TELEGRAM_SAFE_MESSAGE_LIMIT,
) -> None:
    """Отправляет Telegram-ответ и не даёт ошибке отправки уронить handler."""
    await safe_send_async(
        lambda: send_telegram_reply(message, text, limit=limit),
        logger=logger,
        channel="Telegram",
        target_id=str(message.chat.id),
    )


def split_telegram_message(text: str, *, limit: int = TELEGRAM_SAFE_MESSAGE_LIMIT) -> list[str]:
    """Делит текст на части, не превышающие безопасный лимит Telegram.

    Args:
        text: Исходный ответ.
        limit: Максимальная длина одного фрагмента.

    Returns:
        Непустой список фрагментов для последовательной отправки.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = _find_split_position(remaining, limit)
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    return chunks


def _find_split_position(text: str, limit: int) -> int:
    """Находит позицию разреза по абзацу, строке или пробелу."""
    window = text[:limit]
    for separator in ("\n\n", "\n", " "):
        position = window.rfind(separator)
        if position > 0:
            return position + len(separator)
    return limit


def _should_send_processing_ack(text: str) -> bool:
    """Определяет, будет ли сообщение запускать долгую обработку."""
    stripped_text = text.strip()
    return stripped_text.startswith("/reanalyze") or (
        extract_first_supported_url(stripped_text) is not None
    )


def _load_aiogram() -> Any:
    """Загружает `aiogram` только при реальном запуске Telegram adapter."""
    try:
        import aiogram
        import aiogram.filters
    except ModuleNotFoundError as error:
        raise TelegramBotError("aiogram is not installed") from error

    return aiogram
