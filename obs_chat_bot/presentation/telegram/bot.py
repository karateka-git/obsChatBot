from __future__ import annotations

import asyncio
import logging
from typing import Any


class TelegramBotError(RuntimeError):
    """Ошибка запуска Telegram adapter."""


def run_telegram_bot(*, token: str, logger: logging.Logger) -> None:
    """Запускает Telegram-бота в polling-режиме.

    Args:
        token: Telegram Bot API token.
        logger: Logger для сообщений adapter.

    Raises:
        TelegramBotError: Если `aiogram` недоступен или polling завершился ошибкой.
    """
    try:
        asyncio.run(_run_telegram_bot(token=token, logger=logger))
    except TelegramBotError:
        raise
    except Exception as error:
        raise TelegramBotError(f"Telegram bot failed: {error}") from error


async def _run_telegram_bot(*, token: str, logger: logging.Logger) -> None:
    """Асинхронно запускает polling Telegram-бота."""
    aiogram = _load_aiogram()
    bot = aiogram.Bot(token=token)
    dispatcher = aiogram.Dispatcher()

    _register_handlers(dispatcher, aiogram)

    logger.info("Telegram bot polling started")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def _register_handlers(dispatcher: Any, aiogram: Any) -> None:
    """Регистрирует минимальные handlers Telegram adapter."""
    router = aiogram.Router()

    @router.message(aiogram.filters.Command("start"))
    async def handle_start(message: Any) -> None:
        """Отвечает на стартовую команду Telegram-бота."""
        await message.answer("obsChatBot запущен. Отправь ссылку на статью.")

    @router.message()
    async def handle_text(message: Any) -> None:
        """Временно подтверждает получение сообщения до подключения pipeline."""
        await message.answer("Сообщение получено. Обработка ссылок появится в следующем шаге.")

    dispatcher.include_router(router)


def _load_aiogram() -> Any:
    """Загружает `aiogram` только при реальном запуске Telegram adapter."""
    try:
        import aiogram
        import aiogram.filters
    except ModuleNotFoundError as error:
        raise TelegramBotError("aiogram is not installed") from error

    return aiogram
