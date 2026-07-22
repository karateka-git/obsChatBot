"""Тесты VK presentation adapter."""

import logging
import unittest
from unittest.mock import patch

from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageResult,
)
from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionCompletion,
    GitHubConnectionCompletionStatus,
)
from obs_chat_bot.presentation.vk.bot import (
    VkApiClient,
    VkBotError,
    _handle_update,
    split_vk_message,
)


class FakeVkClient:
    """Fake VK client для проверки adapter без реального VK API."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    def send_message(self, *, peer_id: int, text: str) -> None:
        """Запоминает отправленное сообщение."""
        self.messages.append((peer_id, text))


class FailingVkClient(FakeVkClient):
    """Fake VK client, который имитирует ошибку отправки."""

    def send_message(self, *, peer_id: int, text: str) -> None:
        """Имитирует ошибку VK API при отправке сообщения."""
        raise VkBotError("send failed")


class FakeHttpResponse:
    """Минимальный context manager HTTP-ответа для тестов VK API."""

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        """Возвращает успешный JSON-ответ VK API."""
        return b'{"response": 1}'


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

        def processor(
            message: IncomingMessage,
            _completion_handler,
        ) -> ProcessIncomingMessageResult:
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

    def test_handle_update_does_not_raise_when_vk_send_fails(self) -> None:
        """Ошибка отправки VK-сообщения логируется и не роняет adapter."""
        client = FailingVkClient()
        logger = logging.getLogger("test.vk.safe_send")

        def processor(
            _message: IncomingMessage,
            _completion_handler,
        ) -> ProcessIncomingMessageResult:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_URL_MISSING
            )

        with self.assertLogs(logger, level="ERROR") as logs:
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
                logger=logger,
            )
        self.assertIn("VK message send failed", logs.output[0])

    def test_handle_update_completion_callback_replies_to_same_peer(self) -> None:
        """Фоновый GitHub callback отправляет итог в исходный VK peer."""
        client = FakeVkClient()
        completion_handlers = []

        def processor(_message, completion_handler):
            completion_handlers.append(completion_handler)
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_STARTED
            )

        _handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "id": 11,
                        "peer_id": 22,
                        "from_id": 33,
                        "text": "/github_connect",
                    }
                },
            },
            incoming_message_processor=processor,
            client=client,
            logger=logging.getLogger("test.vk.github_completion"),
        )
        completion_handlers[0](
            GitHubConnectionCompletion(
                GitHubConnectionCompletionStatus.CONNECTED,
                installation_count=1,
            )
        )

        self.assertEqual(client.messages[-1][0], 22)
        self.assertIn("аккаунт успешно подключён", client.messages[-1][1])
        self.assertNotIn("установок", client.messages[-1][1])

    def test_api_call_sends_vk_method_params_in_post_body(self) -> None:
        """VK API methods send params in POST body, not in request URI."""
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeHttpResponse()

        client = VkApiClient(token="token")
        with patch("obs_chat_bot.presentation.vk.bot.urlopen", fake_urlopen):
            client.send_message(peer_id=22, text="hello")

        request = captured["request"]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "https://api.vk.com/method/messages.send")
        self.assertIn(b"message=hello", request.data)
        self.assertIn(b"access_token=token", request.data)


if __name__ == "__main__":
    unittest.main()
