"""Общие helpers для безопасной отправки ответов во внешние каналы."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable


def safe_send(
    send: Callable[[], None],
    *,
    logger: logging.Logger,
    channel: str,
    target_id: str,
) -> None:
    """Выполняет синхронную отправку и логирует ошибку без проброса наружу.

    Args:
        send: Функция, которая отправляет сообщение во внешний канал.
        logger: Logger adapter'а.
        channel: Название внешнего канала для диагностики.
        target_id: ID получателя или чата во внешнем канале.
    """
    try:
        send()
    except Exception as error:
        logger.error(
            "%s message send failed: target_id=%s error=%s",
            channel,
            target_id,
            error,
        )


async def safe_send_async(
    send: Callable[[], Awaitable[None]],
    *,
    logger: logging.Logger,
    channel: str,
    target_id: str,
) -> None:
    """Выполняет асинхронную отправку и логирует ошибку без проброса наружу.

    Args:
        send: Coroutine factory, которая отправляет сообщение во внешний канал.
        logger: Logger adapter'а.
        channel: Название внешнего канала для диагностики.
        target_id: ID получателя или чата во внешнем канале.
    """
    try:
        await send()
    except Exception as error:
        logger.error(
            "%s message send failed: target_id=%s error=%s",
            channel,
            target_id,
            error,
        )
