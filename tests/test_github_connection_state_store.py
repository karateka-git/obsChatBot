"""Интеграционные тесты общего SQLite-состояния подключения GitHub."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.github_connection_state_store import (
    SQLiteGitHubConnectionStateStore,
)
from obs_chat_bot.data.sqlite.github_installation_writer import (
    SQLiteGitHubAccountAccessWriter,
)
from obs_chat_bot.data.sqlite.migration_runner import apply_migrations
from tests.sqlite_helpers import ensure_app_user


class GitHubConnectionStateStoreTest(unittest.TestCase):
    """Проверяет подтверждение и межпроцессный claim через разные соединения."""

    def test_account_confirmation_and_attempt_are_shared(self) -> None:
        """Два экземпляра видят один аккаунт, TTL-подтверждение и один claim."""
        now = datetime.now(UTC)
        with TemporaryDirectory(prefix="obs-chat-bot-github-state-") as directory:
            database_path = Path(directory) / "test.db"
            with connect_database(database_path) as connection:
                apply_migrations(connection)
                ensure_app_user(connection)
            SQLiteGitHubAccountAccessWriter(database_path).replace_for_user(
                app_user_id=1,
                github_user_id=777,
                login="octocat",
                installation_ids={101},
            )
            first = SQLiteGitHubConnectionStateStore(database_path)
            second = SQLiteGitHubConnectionStateStore(database_path)

            first.request_reconnect(
                app_user_id=1,
                account_login="octocat",
                expires_at=now + timedelta(minutes=10),
            )
            confirmation = second.find_reconnect_confirmation(
                app_user_id=1,
                now=now,
            )
            acquired = first.acquire_attempt(
                app_user_id=1,
                owner="tg-catcher",
                now=now,
                expires_at=now + timedelta(minutes=20),
            )
            blocked = second.acquire_attempt(
                app_user_id=1,
                owner="vk-catcher",
                now=now,
                expires_at=now + timedelta(minutes=20),
            )
            second.release_attempt(app_user_id=1, owner="vk-catcher")

            self.assertEqual(first.get_account(1).login, "octocat")
            self.assertEqual(confirmation.account_login, "octocat")
            self.assertTrue(acquired)
            self.assertFalse(blocked)
            self.assertTrue(second.has_active_attempt(app_user_id=1, now=now))

            first.release_attempt(app_user_id=1, owner="tg-catcher")
            self.assertFalse(second.has_active_attempt(app_user_id=1, now=now))
            self.assertIsNone(
                second.find_reconnect_confirmation(
                    app_user_id=1,
                    now=now + timedelta(minutes=10),
                )
            )


if __name__ == "__main__":
    unittest.main()
