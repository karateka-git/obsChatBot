from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from random import randint
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from obs_chat_bot.application.articles.incoming_messages import IncomingMessage
from obs_chat_bot.application.articles.url_extraction import extract_first_supported_url
from obs_chat_bot.application.incoming.processing import ProcessIncomingMessageResult
from obs_chat_bot.application.vaults.github_models import GitHubConnectionCompletion
from obs_chat_bot.application.vaults.ports import GitHubConnectionCompletionHandler
from obs_chat_bot.presentation.telegram.bot import PROCESSING_ACK_TEXT
from obs_chat_bot.presentation.shared.responses import (
    format_github_connection_completion,
    format_incoming_message_result,
)
from obs_chat_bot.presentation.shared.safe_send import safe_send


VK_API_VERSION = "5.199"
VK_API_BASE_URL = "https://api.vk.com/method"
VK_SAFE_MESSAGE_LIMIT = 3500
VK_LONG_POLL_WAIT_SECONDS = 25
IncomingMessageProcessor = Callable[
    [IncomingMessage, GitHubConnectionCompletionHandler | None],
    ProcessIncomingMessageResult,
]


class VkBotError(RuntimeError):
    """Ошибка запуска или работы VK adapter."""


def run_vk_bot(
    *,
    token: str,
    group_id: int,
    incoming_message_processor: IncomingMessageProcessor,
    logger: logging.Logger,
    client: VkApiClient | None = None,
) -> None:
    """Запускает VK Bots Long Poll adapter.

    Args:
        token: VK group access token.
        group_id: ID группы VK.
        incoming_message_processor: Общий processor входящих сообщений.
        logger: Logger для runtime-событий.
        client: Optional VK API client для тестов.
    """
    api_client = client or VkApiClient(token=token)
    long_poll = api_client.get_long_poll_server(group_id=group_id)
    logger.info("VK bot long polling started for group_id=%s", group_id)

    while True:
        try:
            payload = api_client.wait_long_poll(long_poll)
        except VkBotError as error:
            logger.error("VK long poll request failed: %s", error)
            time.sleep(1)
            long_poll = api_client.get_long_poll_server(group_id=group_id)
            continue

        if "failed" in payload:
            long_poll = _recover_long_poll(payload, long_poll, group_id, api_client)
            continue

        long_poll = LongPollServer(
            server=long_poll.server,
            key=long_poll.key,
            ts=str(payload.get("ts", long_poll.ts)),
        )
        for update in payload.get("updates", []):
            try:
                _handle_update(
                    update,
                    incoming_message_processor=incoming_message_processor,
                    client=api_client,
                    logger=logger,
                )
            except Exception as error:
                logger.error("VK update handling failed: %s", error)


class LongPollServer:
    """Параметры VK Bots Long Poll server."""

    def __init__(self, *, server: str, key: str, ts: str) -> None:
        self.server = server
        self.key = key
        self.ts = ts


class VkApiClient:
    """Минимальный VK API client для Bots Long Poll и отправки сообщений."""

    def __init__(self, *, token: str, api_version: str = VK_API_VERSION) -> None:
        if not token.strip():
            raise ValueError("token must not be empty")
        self._token = token
        self._api_version = api_version

    def get_long_poll_server(self, *, group_id: int) -> LongPollServer:
        """Получает VK Bots Long Poll server для группы."""
        response = self._api_call(
            "groups.getLongPollServer",
            {"group_id": str(group_id)},
        )
        data = response.get("response")
        if not isinstance(data, dict):
            raise VkBotError("VK long poll server response has unexpected format")
        return LongPollServer(
            server=str(data["server"]),
            key=str(data["key"]),
            ts=str(data["ts"]),
        )

    def wait_long_poll(self, long_poll: LongPollServer) -> dict[str, Any]:
        """Ожидает события VK Long Poll."""
        params = urlencode(
            {
                "act": "a_check",
                "key": long_poll.key,
                "ts": long_poll.ts,
                "wait": str(VK_LONG_POLL_WAIT_SECONDS),
            }
        )
        return self._request_json(f"{long_poll.server}?{params}")

    def send_message(self, *, peer_id: int, text: str) -> None:
        """Отправляет текстовое сообщение VK peer."""
        for chunk in split_vk_message(text):
            self._api_call(
                "messages.send",
                {
                    "peer_id": str(peer_id),
                    "message": chunk,
                    "random_id": str(randint(1, 2_147_483_647)),
                },
            )

    def _api_call(self, method: str, params: dict[str, str]) -> dict[str, Any]:
        api_params = dict(params)
        api_params["access_token"] = self._token
        api_params["v"] = self._api_version
        encoded_params = urlencode(api_params).encode("utf-8")
        request = Request(
            f"{VK_API_BASE_URL}/{method}",
            data=encoded_params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._request_json(request)

    def _request_json(self, request: str | Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=VK_LONG_POLL_WAIT_SECONDS + 5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise VkBotError(f"VK request failed: {error}") from error

        if not isinstance(payload, dict):
            raise VkBotError("VK response is not an object")
        if "error" in payload:
            raise VkBotError(f"VK API error: {payload['error']}")
        return payload


def split_vk_message(text: str, *, limit: int = VK_SAFE_MESSAGE_LIMIT) -> list[str]:
    """Делит длинный VK-ответ на безопасные части."""
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


def _handle_update(
    update: dict[str, Any],
    *,
    incoming_message_processor: IncomingMessageProcessor,
    client: VkApiClient,
    logger: logging.Logger,
) -> None:
    if update.get("type") != "message_new":
        return
    object_data = update.get("object")
    if not isinstance(object_data, dict):
        return
    message = object_data.get("message")
    if not isinstance(message, dict):
        return
    text = str(message.get("text") or "")
    peer_id = _require_int(message.get("peer_id"), "peer_id")
    message_id = _require_int(message.get("id"), "id")
    from_id = _require_int(message.get("from_id"), "from_id")

    if not text.strip():
        _safe_send_vk_message(
            client,
            peer_id=peer_id,
            text="Пришли текстовое сообщение со ссылкой на статью.",
            logger=logger,
        )
        return
    if _should_send_processing_ack(text):
        _safe_send_vk_message(
            client,
            peer_id=peer_id,
            text=PROCESSING_ACK_TEXT,
            logger=logger,
        )

    incoming_message = IncomingMessage(
        channel="vk",
        chat_id=str(peer_id),
        message_id=str(message_id),
        text=text,
        external_user_id=str(from_id),
    )
    completion_handler = _create_vk_github_completion_handler(
        client,
        peer_id=peer_id,
        logger=logger,
    )
    result = incoming_message_processor(incoming_message, completion_handler)
    if result.error is not None:
        logger.error("VK incoming message processing failed: %s", result.error)
    _safe_send_vk_message(
        client,
        peer_id=peer_id,
        text=format_incoming_message_result(result),
        logger=logger,
    )


def _safe_send_vk_message(
    client: Any,
    *,
    peer_id: int,
    text: str,
    logger: logging.Logger,
) -> None:
    """Отправляет VK-сообщение и не даёт ошибке отправки уронить polling."""
    safe_send(
        lambda: client.send_message(peer_id=peer_id, text=text),
        logger=logger,
        channel="VK",
        target_id=str(peer_id),
    )


def _create_vk_github_completion_handler(
    client: Any,
    *,
    peer_id: int,
    logger: logging.Logger,
) -> GitHubConnectionCompletionHandler:
    """Создаёт callback итогового ответа в исходный VK peer."""

    def notify(completion: GitHubConnectionCompletion) -> None:
        _safe_send_vk_message(
            client,
            peer_id=peer_id,
            text=format_github_connection_completion(completion),
            logger=logger,
        )

    return notify


def _recover_long_poll(
    payload: dict[str, Any],
    long_poll: LongPollServer,
    group_id: int,
    client: VkApiClient,
) -> LongPollServer:
    failed = payload.get("failed")
    if failed == 1:
        return LongPollServer(
            server=long_poll.server,
            key=long_poll.key,
            ts=str(payload.get("ts", long_poll.ts)),
        )
    return client.get_long_poll_server(group_id=group_id)


def _should_send_processing_ack(text: str) -> bool:
    stripped_text = text.strip()
    return stripped_text.startswith("/reanalyze") or (
        extract_first_supported_url(stripped_text) is not None
    )


def _find_split_position(text: str, limit: int) -> int:
    window = text[:limit]
    for separator in ("\n\n", "\n", " "):
        position = window.rfind(separator)
        if position > 0:
            return position + len(separator)
    return limit


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise VkBotError(f"VK message field is not int: {field_name}")
    return value
