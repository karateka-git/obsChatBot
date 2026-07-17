from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Callable

from obs_chat_bot.application.users.ports import (
    AppUserRepository,
    ExternalIdentityRepository,
    IdentityLinkTokenRepository,
)
from obs_chat_bot.domain.users.entities import AppUser, IncomingIdentity


class UserIdentityError(RuntimeError):
    """Базовая ошибка сценариев регистрации и привязки каналов."""


class IdentityAlreadyBoundError(UserIdentityError):
    """Ошибка попытки привязать канал, который уже связан с пользователем."""


class InvalidLinkCodeError(UserIdentityError):
    """Ошибка использования несуществующего, просроченного или погашенного кода."""


@dataclass(frozen=True, slots=True)
class CreatedLinkCode:
    """Одноразовый код привязки и срок его действия."""

    code: str
    expires_at: datetime


class UserIdentityService:
    """Координирует регистрацию пользователей и привязку внешних каналов."""

    def __init__(
        self,
        *,
        app_user_repository: AppUserRepository,
        external_identity_repository: ExternalIdentityRepository,
        link_token_repository: IdentityLinkTokenRepository,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        token_ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        self._app_user_repository = app_user_repository
        self._external_identity_repository = external_identity_repository
        self._link_token_repository = link_token_repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: token_urlsafe(6))
        self._token_ttl = token_ttl

    def resolve(self, identity: IncomingIdentity) -> AppUser | None:
        """Возвращает внутреннего пользователя для внешней личности."""
        external_identity = self._external_identity_repository.find(identity)
        if external_identity is None:
            return None

        self._external_identity_repository.touch(identity)
        return self._app_user_repository.get_by_id(external_identity.app_user_id)

    def register(self, identity: IncomingIdentity) -> AppUser:
        """Создает нового пользователя и привязывает к нему текущий канал."""
        existing = self.resolve(identity)
        if existing is not None:
            return existing

        app_user = self._app_user_repository.create(display_name=identity.display_name)
        self._external_identity_repository.create(
            app_user_id=app_user.id,
            identity=identity,
        )
        return app_user

    def create_link_code(self, app_user_id: int) -> CreatedLinkCode:
        """Создает одноразовый код для привязки нового канала к пользователю."""
        if app_user_id <= 0:
            raise ValueError("app_user_id must be positive")

        code = self._token_factory()
        expires_at = self._clock() + self._token_ttl
        self._link_token_repository.create(
            app_user_id=app_user_id,
            token_hash=_hash_code(code),
            expires_at=expires_at,
        )
        return CreatedLinkCode(code=code, expires_at=expires_at)

    def link(self, *, code: str, identity: IncomingIdentity) -> AppUser:
        """Привязывает текущий канал к пользователю по одноразовому коду."""
        if self.resolve(identity) is not None:
            raise IdentityAlreadyBoundError("External identity is already bound")

        app_user_id = self._link_token_repository.consume(
            token_hash=_hash_code(code.strip()),
            now=self._clock(),
        )
        if app_user_id is None:
            raise InvalidLinkCodeError("Link code is invalid or expired")

        self._external_identity_repository.create(
            app_user_id=app_user_id,
            identity=identity,
        )
        app_user = self._app_user_repository.get_by_id(app_user_id)
        if app_user is None:
            raise InvalidLinkCodeError("Link code points to missing user")
        return app_user


def _hash_code(code: str) -> str:
    """Возвращает SHA-256 хеш одноразового кода привязки."""
    return sha256(code.encode("utf-8")).hexdigest()
