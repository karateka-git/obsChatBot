from __future__ import annotations

import asyncio
import logging
from typing import Any

from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.incoming.processing import ProcessIncomingMessageUseCase
from obs_chat_bot.presentation.telegram.responses import (
    format_incoming_message_result,
)


class TelegramBotError(RuntimeError):
    """Ошибка запуска Telegram adapter."""


def run_telegram_bot(
    *,
    token: str,
    incoming_message_use_case: ProcessIncomingMessageUseCase,
    logger: logging.Logger,
) -> None:
    """Запускает Telegram-бота в polling-режиме."""
    try:
        asyncio.run(
            _run_telegram_bot(
                token=token,
                incoming_message_use_case=incoming_message_use_case,
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
    incoming_message_use_case: ProcessIncomingMessageUseCase,
    logger: logging.Logger,
) -> None:
    """Асинхронно запускает polling Telegram-бота."""
    aiogram = _load_aiogram()
    bot = aiogram.Bot(token=token)
    dispatcher = aiogram.Dispatcher()

    _register_handlers(
        dispatcher,
        aiogram,
        incoming_message_use_case=incoming_message_use_case,
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
    incoming_message_use_case: ProcessIncomingMessageUseCase,
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
        result = incoming_message_use_case.execute(incoming_message)
        if result.error is not None:
            logger.error("Telegram incoming message processing failed: %s", result.error)
        reply = format_incoming_message_result(result)
        await message.answer(reply)

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


def _load_aiogram() -> Any:
    """Загружает `aiogram` только при реальном запуске Telegram adapter."""
    try:
        import aiogram
        import aiogram.filters
    except ModuleNotFoundError as error:
        raise TelegramBotError("aiogram is not installed") from error

    return aiogram
