from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CommandSection(StrEnum):
    """Раздел пользовательских команд в общей справке."""

    BASIC = "Основные"
    CHANNEL_LINKING = "Связь Telegram и VK"
    GITHUB = "Obsidian vault"
    ARTICLES = "Статьи"


class ChatCommand(StrEnum):
    """Описывает поддерживаемую chat-команду и её строку справки.

    Каждый элемент является единым источником имени, аргументов, раздела и
    пользовательского описания. Новый элемент автоматически попадает в `/help`.
    """

    section: CommandSection
    arguments_hint: str
    description: str

    def __new__(
        cls,
        value: str,
        section: CommandSection,
        arguments_hint: str,
        description: str,
    ) -> ChatCommand:
        member = str.__new__(cls, value)
        member._value_ = value
        member.section = section
        member.arguments_hint = arguments_hint
        member.description = description
        return member

    START = (
        "/start",
        CommandSection.BASIC,
        "",
        "проверить подключение бота и канала",
    )
    HELP = (
        "/help",
        CommandSection.BASIC,
        "",
        "показать список доступных команд",
    )
    REGISTER = (
        "/register",
        CommandSection.BASIC,
        "",
        "зарегистрироваться и подключить Obsidian vault",
    )
    NAME = (
        "/name",
        CommandSection.BASIC,
        "<имя>",
        "изменить имя или название профиля",
    )
    STATUS = (
        "/status",
        CommandSection.BASIC,
        "",
        "показать состояние подключения",
    )
    LINK_CODE = (
        "/link_code",
        CommandSection.CHANNEL_LINKING,
        "",
        "создать код привязки второго канала",
    )
    LINK = (
        "/link",
        CommandSection.CHANNEL_LINKING,
        "<код>",
        "привязать канал по полученному коду",
    )
    GITHUB_STATUS = (
        "/github_status",
        CommandSection.GITHUB,
        "",
        "показать состояние локальной копии vault",
    )
    GITHUB_SYNC = (
        "/github_sync",
        CommandSection.GITHUB,
        "",
        "проверить GitHub и синхронизировать vault",
    )
    REANALYZE = (
        "/reanalyze",
        CommandSection.ARTICLES,
        "<ID статьи>",
        "выполнить анализ статьи повторно",
    )

    @property
    def usage(self) -> str:
        """Возвращает имя команды с подсказкой обязательных аргументов."""
        if not self.arguments_hint:
            return self.value
        return f"{self.value} {self.arguments_hint}"

    def __str__(self) -> str:
        """Форматирует одну строку Markdown для `/help`."""
        return f"`{self.usage}` — {self.description}"


@dataclass(frozen=True, slots=True)
class ParsedChatCommand:
    """Содержит распознанную команду и необработанную строку аргументов."""

    command: ChatCommand
    arguments: str = ""

    @classmethod
    def parse(cls, text: str) -> ParsedChatCommand | None:
        """Распознаёт точное имя известной команды.

        Args:
            text: Полный текст входящего сообщения.

        Returns:
            Команду с аргументами или `None` для обычного текста и неизвестной
            slash-команды.
        """
        parts = text.strip().split(maxsplit=1)
        if not parts:
            return None
        try:
            command = ChatCommand(parts[0])
        except ValueError:
            return None
        arguments = parts[1].strip() if len(parts) == 2 else ""
        return cls(command=command, arguments=arguments)
