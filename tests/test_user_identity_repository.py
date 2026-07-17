"""Тесты SQLite-хранилища identity и сценария привязки каналов."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from obs_chat_bot.application.users.identity import UserIdentityService
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.migration_runner import apply_migrations
from obs_chat_bot.data.sqlite.user_identity_repository import (
    SQLiteAppUserRepository,
    SQLiteExternalIdentityRepository,
    SQLiteIdentityLinkTokenRepository,
)
from obs_chat_bot.domain.users.entities import IncomingIdentity


class SQLiteUserIdentityRepositoryTest(unittest.TestCase):
    """Проверяет регистрацию пользователей и привязку каналов."""

    def test_register_creates_user_and_resolves_same_identity(self) -> None:
        """Регистрация создает внутреннего пользователя и связь с каналом."""
        with TemporaryDirectory(prefix="obs-chat-bot-identity-") as directory:
            with connect_database(Path(directory) / "test.db") as connection:
                apply_migrations(connection)
                service = _service(connection)

                user = service.register(_identity("telegram", "tg-1", "chat-1"))
                resolved = service.resolve(_identity("telegram", "tg-1", "chat-1"))

        self.assertEqual(resolved, user)

    def test_link_code_binds_second_channel_to_same_user(self) -> None:
        """Одноразовый код привязывает новый канал к существующему пользователю."""
        with TemporaryDirectory(prefix="obs-chat-bot-identity-") as directory:
            with connect_database(Path(directory) / "test.db") as connection:
                apply_migrations(connection)
                service = _service(connection)

                user = service.register(_identity("telegram", "tg-1", "chat-1"))
                link_code = service.create_link_code(user.id)
                linked = service.link(
                    code=link_code.code,
                    identity=_identity("vk", "vk-1", "chat-2"),
                )
                resolved = service.resolve(_identity("vk", "vk-1", "chat-2"))

        self.assertEqual(linked, user)
        self.assertEqual(resolved, user)


def _service(connection) -> UserIdentityService:
    """Создает identity service с предсказуемыми часами и кодом."""
    return UserIdentityService(
        app_user_repository=SQLiteAppUserRepository(connection),
        external_identity_repository=SQLiteExternalIdentityRepository(connection),
        link_token_repository=SQLiteIdentityLinkTokenRepository(connection),
        clock=lambda: datetime(2026, 7, 17, tzinfo=UTC),
        token_factory=lambda: "ABC123",
        token_ttl=timedelta(minutes=10),
    )


def _identity(channel: str, user_id: str, chat_id: str) -> IncomingIdentity:
    """Создает внешнюю identity для тестов."""
    return IncomingIdentity(
        channel=channel,
        external_user_id=user_id,
        external_chat_id=chat_id,
        username=f"{channel}_{user_id}",
        display_name="Test User",
    )


if __name__ == "__main__":
    unittest.main()
