from __future__ import annotations

from datetime import datetime
from pathlib import Path

from obs_chat_bot.application.vaults.ports import GitHubConnectionStateStore
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.vault_mappers import (
    format_utc_timestamp,
    github_account_from_row,
    github_reconnect_confirmation_from_row,
)
from obs_chat_bot.domain.vaults.entities import (
    GitHubAccount,
    GitHubReconnectConfirmation,
)


class SQLiteGitHubConnectionStateStore(GitHubConnectionStateStore):
    """Хранит account, confirmation и claim через короткие SQLite-соединения."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get_account(self, app_user_id: int) -> GitHubAccount | None:
        """Возвращает подключённый GitHub-аккаунт пользователя."""
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT app_user_id, github_user_id, login, created_at, updated_at
                FROM github_accounts
                WHERE app_user_id = ?
                """,
                (app_user_id,),
            ).fetchone()
        return github_account_from_row(row) if row is not None else None

    def request_reconnect(
        self,
        *,
        app_user_id: int,
        account_login: str,
        expires_at: datetime,
    ) -> None:
        """Сохраняет или продлевает подтверждение замены GitHub-аккаунта."""
        with connect_database(self._database_path) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO github_reconnect_confirmations (
                        app_user_id, account_login, expires_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT (app_user_id) DO UPDATE SET
                        account_login = excluded.account_login,
                        expires_at = excluded.expires_at,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (app_user_id, account_login, format_utc_timestamp(expires_at)),
                )

    def find_reconnect_confirmation(
        self,
        *,
        app_user_id: int,
        now: datetime,
    ) -> GitHubReconnectConfirmation | None:
        """Возвращает активное подтверждение и очищает истёкшую строку."""
        now_text = format_utc_timestamp(now)
        with connect_database(self._database_path) as connection:
            with connection:
                connection.execute(
                    """
                    DELETE FROM github_reconnect_confirmations
                    WHERE app_user_id = ? AND expires_at <= ?
                    """,
                    (app_user_id, now_text),
                )
                row = connection.execute(
                    """
                    SELECT app_user_id, account_login, expires_at, created_at
                    FROM github_reconnect_confirmations
                    WHERE app_user_id = ?
                    """,
                    (app_user_id,),
                ).fetchone()
        return (
            github_reconnect_confirmation_from_row(row)
            if row is not None
            else None
        )

    def delete_reconnect_confirmation(self, app_user_id: int) -> None:
        """Удаляет ожидающее подтверждение переподключения."""
        with connect_database(self._database_path) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM github_reconnect_confirmations WHERE app_user_id = ?",
                    (app_user_id,),
                )

    def acquire_attempt(
        self,
        *,
        app_user_id: int,
        owner: str,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        """Атомарно захватывает или отказывает в межпроцессном claim."""
        with connect_database(self._database_path) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM github_connection_attempts WHERE expires_at <= ?",
                    (format_utc_timestamp(now),),
                )
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO github_connection_attempts (
                        app_user_id, owner, acquired_at, expires_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        app_user_id,
                        owner,
                        format_utc_timestamp(now),
                        format_utc_timestamp(expires_at),
                    ),
                )
        return cursor.rowcount == 1

    def has_active_attempt(self, *, app_user_id: int, now: datetime) -> bool:
        """Проверяет shared claim, попутно удаляя истёкшие claims."""
        with connect_database(self._database_path) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM github_connection_attempts WHERE expires_at <= ?",
                    (format_utc_timestamp(now),),
                )
                row = connection.execute(
                    """
                    SELECT 1 FROM github_connection_attempts WHERE app_user_id = ?
                    """,
                    (app_user_id,),
                ).fetchone()
        return row is not None

    def release_attempt(self, *, app_user_id: int, owner: str) -> None:
        """Освобождает shared claim только совпадающим владельцем."""
        with connect_database(self._database_path) as connection:
            with connection:
                connection.execute(
                    """
                    DELETE FROM github_connection_attempts
                    WHERE app_user_id = ? AND owner = ?
                    """,
                    (app_user_id, owner),
                )
