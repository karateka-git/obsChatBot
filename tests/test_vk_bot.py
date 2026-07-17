"""Тесты VK presentation adapter."""

import logging
import unittest

from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageResult,
)
from obs_chat_bot.presentation.vk.bot import _handle_update, split_vk_message


class FakeVkClient:
    """Fake VK client для проверки adapter без реального VK API."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    def send_message(self, *, peer_id: int, text: str) -> None:
        """Запоминает отправленное сообщение."""
        self.messages.append((peer_id, text))


class VkBotTest(unittest.TestCase):
    """Проверяет helpers VK adapter."""

    def test_split_vk_message_keeps_chunks_under_limit(self) -> None:
        """Длинный VK-ответ делится на безопасные фрагменты."""
        chunks = split_vk_message("alpha beta gamma delta", limit=10)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 10 for chunk in chunks))
        self.assertEqual(" ".join(chunks), "alpha beta gamma delta")

    def test_handle_update_converts_vk_message_to_incoming_message(self) -> None:
        """VK update превращается в channel-agnostic IncomingMessage."""
        client = FakeVkClient()
        processed: list[IncomingMessage] = []

        def processor(message: IncomingMessage) -> ProcessIncomingMessageResult:
            processed.append(message)
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_URL_MISSING
            )

        _handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "id": 11,
                        "peer_id": 22,
                        "from_id": 33,
                        "text": "hello",
                    }
                },
            },
            incoming_message_processor=processor,
            client=client,
            logger=logging.getLogger("test"),
        )

        self.assertEqual(processed[0].channel, "vk")
        self.assertEqual(processed[0].chat_id, "22")
        self.assertEqual(processed[0].message_id, "11")
        self.assertEqual(processed[0].external_user_id, "33")
        self.assertEqual(client.messages[0][0], 22)
        self.assertIn("Пришли ссылку", client.messages[0][1])


if __name__ == "__main__":
    unittest.main()
