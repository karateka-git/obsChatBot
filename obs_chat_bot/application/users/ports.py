from __future__ import annotations

from datetime import datetime
from typing import Protocol

from obs_chat_bot.domain.users.entities import AppUser, ExternalIdentity, IncomingIdentity


class AppUserRepository(Protocol):
    """Описывает хранилище внутренних пользователей приложения."""

    def create(self, *, display_name: str | None = None) -> AppUser:
        """Создает нового пользователя приложения."""

    def get_by_id(self, app_user_id: int) -> AppUser | None:
        """Возвращает пользователя по ID или `None`."""


class ExternalIdentityRepository(Protocol):
    """Описывает хранилище связей внутренних пользователей с внешними каналами."""

    def find(self, identity: IncomingIdentity) -> ExternalIdentity | None:
        """Ищет связь по каналу и внешнему ID пользователя."""

    def create(
        self,
        *,
        app_user_id: int,
        identity: IncomingIdentity,
    ) -> ExternalIdentity:
        """Создает связь пользователя приложения с внешней личностью."""

    def touch(self, identity: IncomingIdentity) -> None:
        """Обновляет служебные данные уже известной внешней личности."""


class IdentityLinkTokenRepository(Protocol):
    """Описывает хранилище одноразовых кодов привязки каналов."""

    def create(
        self,
        *,
        app_user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        """Сохраняет одноразовый код привязки."""

    def consume(self, *, token_hash: str, now: datetime) -> int | None:
        """Погашает код и возвращает ID пользователя, если код действителен."""
