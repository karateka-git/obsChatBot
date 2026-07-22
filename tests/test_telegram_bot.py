"""Тесты низкоуровневых helpers Telegram adapter."""

import asyncio
import logging
import unittest

from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionCompletion,
    GitHubConnectionCompletionStatus,
)
from obs_chat_bot.presentation.telegram.bot import (
    _create_telegram_github_completion_handler,
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


class TelegramMessage:
    """Fake Telegram message, сохраняющий отправленные ответы."""

    class Chat:
        """Минимальная модель Telegram chat для helper-теста."""

        id = 42

    chat = Chat()

    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        """Сохраняет отправленный текст."""
        self.answers.append(text)


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

    def test_github_completion_callback_replies_in_telegram_loop(self) -> None:
        """Фоновый callback безопасно возвращается в Telegram event loop."""
        message = TelegramMessage()
        logger = logging.getLogger("test.telegram.github_completion")

        async def run() -> None:
            handler = _create_telegram_github_completion_handler(
                message,
                loop=asyncio.get_running_loop(),
                logger=logger,
            )
            await asyncio.to_thread(
                handler,
                GitHubConnectionCompletion(
                    GitHubConnectionCompletionStatus.CONNECTED,
                    installation_count=1,
                ),
            )
            for _attempt in range(10):
                if message.answers:
                    break
                await asyncio.sleep(0)

        asyncio.run(run())

        self.assertEqual(len(message.answers), 1)
        self.assertIn("аккаунт успешно подключён", message.answers[0])
        self.assertNotIn("установок", message.answers[0])


if __name__ == "__main__":
    unittest.main()
