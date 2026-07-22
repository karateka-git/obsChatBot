"""Тест потокобезопасной записи GitHub installations."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.github_installation_repository import (
    SQLiteGitHubInstallationRepository,
)
from obs_chat_bot.data.sqlite.github_installation_writer import (
    SQLiteGitHubInstallationAccessWriter,
)
from obs_chat_bot.data.sqlite.migration_runner import apply_migrations


class GitHubInstallationWriterTest(unittest.TestCase):
    """Проверяет отдельное SQLite-соединение background worker."""

    def test_writer_opens_fresh_connection_and_persists_only_ids(self) -> None:
        """Writer не переносит user token в SQLite repository."""
        with TemporaryDirectory(prefix="obs-chat-bot-github-writer-") as directory:
            database_path = Path(directory) / "test.db"
            with connect_database(database_path) as connection:
                apply_migrations(connection)

            SQLiteGitHubInstallationAccessWriter(database_path).replace_for_user(
                app_user_id=1,
                installation_ids={101, 102},
            )

            with connect_database(database_path) as connection:
                installations = SQLiteGitHubInstallationRepository(
                    connection
                ).list_for_user(1)

        self.assertEqual(
            [installation.installation_id for installation in installations],
            [101, 102],
        )


if __name__ == "__main__":
    unittest.main()
