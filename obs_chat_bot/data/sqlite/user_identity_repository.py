from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from obs_chat_bot.application.users.ports import (
    AppUserRepository,
    ExternalIdentityRepository,
    IdentityRebindConfirmationRepository,
    IdentityLinkTokenRepository,
)
from obs_chat_bot.domain.users.entities import AppUser, ExternalIdentity, IncomingIdentity


class SQLiteAppUserRepository(AppUserRepository):
    """Хранит внутренних пользователей приложения в SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, *, display_name: str | None = None) -> AppUser:
        """Создает нового пользователя приложения."""
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO app_users (display_name)
                VALUES (?)
                """,
                (display_name,),
            )

        user_id = cursor.lastrowid
        if user_id is None:
            raise RuntimeError("SQLite did not return a new app user id")

        user = self.get_by_id(user_id)
        if user is None:
            raise RuntimeError(f"Created app user could not be read: {user_id}")
        return user

    def get_by_id(self, app_user_id: int) -> AppUser | None:
        """Возвращает пользователя приложения по ID."""
        row = self._connection.execute(
            """
            SELECT id, display_name, created_at
            FROM app_users
            WHERE id = ?
            """,
            (app_user_id,),
        ).fetchone()
        if row is None:
            return None
        return AppUser(
            id=row["id"],
            display_name=row["display_name"],
            created_at=_parse_utc_timestamp(row["created_at"]),
        )

    def delete(self, app_user_id: int) -> None:
        """Удаляет пользователя приложения по ID."""
        with self._connection:
            self._connection.execute(
                "DELETE FROM app_users WHERE id = ?",
                (app_user_id,),
            )


class SQLiteExternalIdentityRepository(ExternalIdentityRepository):
    """Хранит связи пользователей приложения с внешними каналами."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def find(self, identity: IncomingIdentity) -> ExternalIdentity | None:
        """Ищет связь по каналу и внешнему ID пользователя."""
        row = self._connection.execute(
            """
            SELECT
                id,
                app_user_id,
                channel,
                external_user_id,
                external_chat_id,
                username,
                display_name
            FROM external_identities
            WHERE channel = ? AND external_user_id = ?
            """,
            (identity.channel, identity.external_user_id),
        ).fetchone()
        return _external_identity_from_row(row) if row is not None else None

    def create(
        self,
        *,
        app_user_id: int,
        identity: IncomingIdentity,
    ) -> ExternalIdentity:
        """Создает связь внутреннего пользователя с внешней личностью."""
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO external_identities (
                    app_user_id,
                    channel,
                    external_user_id,
                    external_chat_id,
                    username,
                    display_name
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    app_user_id,
                    identity.channel,
                    identity.external_user_id,
                    identity.external_chat_id,
                    identity.username,
                    identity.display_name,
                ),
            )

        identity_id = cursor.lastrowid
        if identity_id is None:
            raise RuntimeError("SQLite did not return a new external identity id")

        created = self.find(identity)
        if created is None:
            raise RuntimeError(
                f"Created external identity could not be read: {identity_id}"
            )
        return created

    def reassign(
        self,
        *,
        app_user_id: int,
        identity: IncomingIdentity,
    ) -> ExternalIdentity:
        """Перепривязывает существующую внешнюю личность к другому пользователю."""
        with self._connection:
            self._connection.execute(
                """
                UPDATE external_identities
                SET
                    app_user_id = ?,
                    external_chat_id = ?,
                    username = ?,
                    display_name = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE channel = ? AND external_user_id = ?
                """,
                (
                    app_user_id,
                    identity.external_chat_id,
                    identity.username,
                    identity.display_name,
                    identity.channel,
                    identity.external_user_id,
                ),
            )

        updated = self.find(identity)
        if updated is None:
            raise RuntimeError("Reassigned external identity could not be read")
        return updated

    def count_for_user(self, app_user_id: int) -> int:
        """Возвращает количество внешних личностей пользователя."""
        row = self._connection.execute(
            """
            SELECT COUNT(*) AS identity_count
            FROM external_identities
            WHERE app_user_id = ?
            """,
            (app_user_id,),
        ).fetchone()
        return int(row["identity_count"])

    def touch(self, identity: IncomingIdentity) -> None:
        """Обновляет чат, имя и время последнего появления внешней личности."""
        with self._connection:
            self._connection.execute(
                """
                UPDATE external_identities
                SET
                    external_chat_id = ?,
                    username = ?,
                    display_name = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE channel = ? AND external_user_id = ?
                """,
                (
                    identity.external_chat_id,
                    identity.username,
                    identity.display_name,
                    identity.channel,
                    identity.external_user_id,
                ),
            )


class SQLiteIdentityLinkTokenRepository(IdentityLinkTokenRepository):
    """Хранит одноразовые коды привязки каналов в SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        app_user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        """Сохраняет одноразовый код привязки."""
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO identity_link_tokens (
                    app_user_id,
                    token_hash,
                    expires_at
                )
                VALUES (?, ?, ?)
                """,
                (app_user_id, token_hash, _format_timestamp(expires_at)),
            )

    def consume(self, *, token_hash: str, now: datetime) -> int | None:
        """Погашает действующий код и возвращает ID пользователя."""
        with self._connection:
            row = self._find_active_row(token_hash=token_hash, now=now)
            if row is None:
                return None

            cursor = self._connection.execute(
                """
                UPDATE identity_link_tokens
                SET used_at = CURRENT_TIMESTAMP
                WHERE id = ? AND used_at IS NULL
                """,
                (row["id"],),
            )
            if cursor.rowcount != 1:
                return None
            return row["app_user_id"]

    def find_active(self, *, token_hash: str, now: datetime) -> int | None:
        """Возвращает ID пользователя для действующего кода без погашения."""
        row = self._find_active_row(token_hash=token_hash, now=now)
        return row["app_user_id"] if row is not None else None

    def _find_active_row(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT id, app_user_id
            FROM identity_link_tokens
            WHERE token_hash = ?
                AND used_at IS NULL
                AND expires_at > ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (token_hash, _format_timestamp(now)),
        ).fetchone()


class SQLiteIdentityRebindConfirmationRepository(IdentityRebindConfirmationRepository):
    """Хранит ожидающие подтверждения перепривязки каналов в SQLite."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(
        self,
        *,
        identity: IncomingIdentity,
        token_hash: str,
        target_app_user_id: int,
        expires_at: datetime,
    ) -> None:
        """Сохраняет ожидающее подтверждение перепривязки канала."""
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO identity_rebind_confirmations (
                    channel,
                    external_user_id,
                    token_hash,
                    target_app_user_id,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(channel, external_user_id) DO UPDATE SET
                    token_hash = excluded.token_hash,
                    target_app_user_id = excluded.target_app_user_id,
                    expires_at = excluded.expires_at,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    identity.channel,
                    identity.external_user_id,
                    token_hash,
                    target_app_user_id,
                    _format_timestamp(expires_at),
                ),
            )

    def find(
        self,
        *,
        identity: IncomingIdentity,
        now: datetime,
    ) -> tuple[str, int] | None:
        """Возвращает активное подтверждение перепривязки канала."""
        row = self._connection.execute(
            """
            SELECT token_hash, target_app_user_id
            FROM identity_rebind_confirmations
            WHERE channel = ?
                AND external_user_id = ?
                AND expires_at > ?
            """,
            (
                identity.channel,
                identity.external_user_id,
                _format_timestamp(now),
            ),
        ).fetchone()
        if row is None:
            return None
        return row["token_hash"], row["target_app_user_id"]

    def delete(self, *, identity: IncomingIdentity) -> None:
        """Удаляет ожидающее подтверждение перепривязки канала."""
        with self._connection:
            self._connection.execute(
                """
                DELETE FROM identity_rebind_confirmations
                WHERE channel = ? AND external_user_id = ?
                """,
                (identity.channel, identity.external_user_id),
            )


def _external_identity_from_row(row: sqlite3.Row) -> ExternalIdentity:
    """Преобразует строку SQLite во внешнюю identity."""
    return ExternalIdentity(
        id=row["id"],
        app_user_id=row["app_user_id"],
        channel=row["channel"],
        external_user_id=row["external_user_id"],
        external_chat_id=row["external_chat_id"],
        username=row["username"],
        display_name=row["display_name"],
    )


def _format_timestamp(value: datetime) -> str:
    """Форматирует timestamp для SQLite в UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _parse_utc_timestamp(value: str) -> datetime:
    """Преобразует SQLite timestamp в timezone-aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
