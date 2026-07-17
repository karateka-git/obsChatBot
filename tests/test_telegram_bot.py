"""Тесты низкоуровневых helpers Telegram adapter."""

import unittest

from obs_chat_bot.presentation.telegram.bot import split_telegram_message


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


if __name__ == "__main__":
    unittest.main()
