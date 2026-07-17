"""Тесты низкоуровневых helpers Telegram adapter."""

import asyncio
import logging
import unittest

from obs_chat_bot.presentation.telegram.bot import (
    safe_send_telegram_reply,
    split_telegram_message,
)


class FailingTelegramMessage:
    """Fake Telegram message, который имитирует ошибку отправки."""

    class Chat:
        """Минимальная модель Telegram chat для helper-теста."""

        id = 42

    chat = Chat()

    async def answer(self, _text: str) -> None:
        """Имитирует ошибку Telegram API при отправке ответа."""
        raise RuntimeError("send failed")


class TelegramBotHelpersTest(unittest.TestCase):
    """Проверяет helpers, не требующие реального Telegram."""

    def test_split_telegram_message_keeps_chunks_under_limit(self) -> None:
        """Длинный ответ делится на безопасные фрагменты."""
        chunks = split_telegram_message("alpha beta gamma delta", limit=10)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 10 for chunk in chunks))
        self.assertEqual(" ".join(chunks), "alpha beta gamma delta")

    def test_split_telegram_message_falls_back_to_hard_split(self) -> None:
        """Слово длиннее лимита режется без бесконечного цикла."""
        chunks = split_telegram_message("abcdefghij", limit=4)

        self.assertEqual(chunks, ["abcd", "efgh", "ij"])

    def test_safe_send_telegram_reply_does_not_raise_when_send_fails(self) -> None:
        """Ошибка отправки Telegram-сообщения логируется и не роняет handler."""
        message = FailingTelegramMessage()
        logger = logging.getLogger("test.telegram.safe_send")

        async def run() -> None:
            await safe_send_telegram_reply(
                message,
                "hello",
                logger=logger,
            )

        with self.assertLogs(logger, level="ERROR") as logs:
            asyncio.run(run())
        self.assertIn("Telegram message send failed", logs.output[0])


if __name__ == "__main__":
    unittest.main()
