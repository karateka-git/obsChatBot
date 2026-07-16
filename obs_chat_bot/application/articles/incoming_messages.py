from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """Представляет входящее сообщение из внешнего канала.

    Модель не зависит от Telegram/VK API и нужна application-слою как единая
    форма пользовательского сообщения.
    """

    channel: str
    chat_id: str
    message_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.channel.strip():
            raise ValueError("channel must not be empty")
        if not self.chat_id.strip():
            raise ValueError("chat_id must not be empty")
        if not self.message_id.strip():
            raise ValueError("message_id must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")


@dataclass(frozen=True, slots=True)
class SavedIncomingMessage:
    """Представляет входящее сообщение, уже сохранённое в хранилище.

    Application-слой использует эту модель, чтобы работать с ID записи без
    знания о конкретной таблице SQLite или другом data-источнике.
    """

    id: int
    channel: str
    chat_id: str
    message_id: str
    text: str
    article_id: int | None = None

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("id must be positive")
        if not self.channel.strip():
            raise ValueError("channel must not be empty")
        if not self.chat_id.strip():
            raise ValueError("chat_id must not be empty")
        if not self.message_id.strip():
            raise ValueError("message_id must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if self.article_id is not None and self.article_id <= 0:
            raise ValueError("article_id must be positive")
