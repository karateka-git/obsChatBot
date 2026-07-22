from __future__ import annotations

from pathlib import Path

from obs_chat_bot.application.vaults.ports import GitHubInstallationAccessWriter
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.github_installation_repository import (
    SQLiteGitHubInstallationRepository,
)


class SQLiteGitHubInstallationAccessWriter(GitHubInstallationAccessWriter):
    """Открывает отдельное SQLite-соединение для фонового Device Flow."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def replace_for_user(
        self,
        *,
        app_user_id: int,
        installation_ids: set[int],
    ) -> None:
        """Сохраняет installations через соединение текущего background thread."""
        with connect_database(self._database_path) as connection:
            SQLiteGitHubInstallationRepository(connection).replace_for_user(
                app_user_id=app_user_id,
                installation_ids=installation_ids,
            )
