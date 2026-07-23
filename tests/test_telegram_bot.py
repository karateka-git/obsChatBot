"""Тесты низкоуровневых helpers Telegram adapter."""

import asyncio
import logging
import unittest

from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageResult,
)
from obs_chat_bot.presentation.telegram.bot import (
    _create_telegram_completion_handler,
    safe_send_telegram_reply,
    split_telegram_message,
)


class FailingTelegramMessage:
    """Fake Telegram message, который имитирует ошибку отправки."""

    class Chat:
        """Минимальная модель Telegram chat для helper-теста."""

        id = 42

    chat = Chat()

    def __init__(self) -> None:
        self.attempts = 0

    async def answer(self, _text: str) -> None:
        """Имитирует ошибку Telegram API при отправке ответа."""
        self.attempts += 1
        raise RuntimeError("send failed")


class TelegramNetworkError(RuntimeError):
    """Имитирует типизированную временную сетевую ошибку aiogram."""


class TelegramRetryAfter(RuntimeError):
    """Имитирует Telegram rate limit с обязательной серверной задержкой."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


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


class FlakyTelegramMessage(TelegramMessage):
    """Один раз роняет выбранный chunk, затем принимает повтор."""

    def __init__(self, failing_chunk: str) -> None:
        super().__init__()
        self.failing_chunk = failing_chunk
        self.calls: list[str] = []
        self.failed = False

    async def answer(self, text: str) -> None:
        """Сохраняет попытку и один раз имитирует временный сетевой сбой."""
        self.calls.append(text)
        if text == self.failing_chunk and not self.failed:
            self.failed = True
            raise TelegramNetworkError("temporary failure")
        self.answers.append(text)


class RateLimitedTelegramMessage(TelegramMessage):
    """Один раз возвращает Telegram `RetryAfter`, затем принимает сообщение."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def answer(self, text: str) -> None:
        """Требует задержку 2.5 секунды перед успешным повтором."""
        self.attempts += 1
        if self.attempts == 1:
            raise TelegramRetryAfter(2.5)
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
        self.assertEqual(message.attempts, 1)

    def test_safe_send_retries_only_failed_telegram_chunk(self) -> None:
        """Временный сбой не дублирует уже отправленные части длинного ответа."""
        message = FlakyTelegramMessage("efgh")
        logger = logging.getLogger("test.telegram.retry")
        delays: list[float] = []

        async def sleeper(delay: float) -> None:
            delays.append(delay)

        async def run() -> None:
            await safe_send_telegram_reply(
                message,
                "abcdefghij",
                logger=logger,
                limit=4,
                sleeper=sleeper,
            )

        with self.assertLogs(logger, level="WARNING") as logs:
            asyncio.run(run())

        self.assertEqual(message.calls, ["abcd", "efgh", "efgh", "ij"])
        self.assertEqual(message.answers, ["abcd", "efgh", "ij"])
        self.assertEqual(delays, [0.5])
        self.assertIn("failed_attempt=1/3", logs.output[0])

    def test_safe_send_respects_telegram_retry_after(self) -> None:
        """Rate limit Telegram задаёт задержку вместо стандартного backoff."""
        message = RateLimitedTelegramMessage()
        logger = logging.getLogger("test.telegram.retry_after")
        delays: list[float] = []

        async def sleeper(delay: float) -> None:
            delays.append(delay)

        async def run() -> None:
            await safe_send_telegram_reply(
                message,
                "hello",
                logger=logger,
                sleeper=sleeper,
            )

        with self.assertLogs(logger, level="WARNING"):
            asyncio.run(run())

        self.assertEqual(message.answers, ["hello"])
        self.assertEqual(message.attempts, 2)
        self.assertEqual(delays, [2.5])

    def test_completion_callback_replies_in_telegram_loop(self) -> None:
        """Фоновый результат безопасно возвращается в Telegram event loop."""
        message = TelegramMessage()
        logger = logging.getLogger("test.telegram.github_completion")

        async def run() -> None:
            handler = _create_telegram_completion_handler(
                message,
                loop=asyncio.get_running_loop(),
                logger=logger,
            )
            await asyncio.to_thread(
                handler,
                ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.GITHUB_APP_REQUIRED,
                    installation_url=(
                        "https://github.com/apps/obs-chat-bot/installations/new"
                    ),
                ),
            )
            for _attempt in range(10):
                if message.answers:
                    break
                await asyncio.sleep(0)

        asyncio.run(run())

        self.assertEqual(len(message.answers), 1)
        self.assertIn("installations/new", message.answers[0])
        self.assertIn("read and write", message.answers[0])


if __name__ == "__main__":
    unittest.main()
