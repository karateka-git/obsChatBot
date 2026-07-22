from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class GitHubDeviceAuthorization:
    """Содержит временный Device Flow challenge для показа пользователю."""

    device_code: str = field(repr=False)
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int

    def __post_init__(self) -> None:
        if not self.device_code.strip():
            raise ValueError("device_code must not be empty")
        if not self.user_code.strip():
            raise ValueError("user_code must not be empty")
        if not self.verification_uri.strip():
            raise ValueError("verification_uri must not be empty")
        if self.expires_in <= 0:
            raise ValueError("expires_in must be positive")
        if self.interval <= 0:
            raise ValueError("interval must be positive")


@dataclass(frozen=True, slots=True)
class GitHubUserAccessToken:
    """Обертывает временный user access token без раскрытия в `repr`."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("value must not be empty")


@dataclass(frozen=True, slots=True)
class GitHubInstallationAccessToken:
    """Обертывает краткоживущий installation token и срок его действия."""

    value: str = field(repr=False)
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("value must not be empty")


class GitHubDevicePollStatus(StrEnum):
    """Результат одной проверки Device Flow authorization."""

    AUTHORIZED = "authorized"  # Пользователь подтвердил код.
    PENDING = "pending"  # Пользователь ещё не подтвердил код.
    SLOW_DOWN = "slow_down"  # GitHub требует увеличить interval polling.
    EXPIRED = "expired"  # Device code больше не действует.
    DENIED = "denied"  # Пользователь явно отклонил авторизацию.


@dataclass(frozen=True, slots=True)
class GitHubDevicePollResult:
    """Содержит статус Device Flow и token только после авторизации."""

    status: GitHubDevicePollStatus
    access_token: GitHubUserAccessToken | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GitHubDevicePollStatus):
            raise TypeError("status must be a GitHubDevicePollStatus")
        if self.status is GitHubDevicePollStatus.AUTHORIZED:
            if self.access_token is None:
                raise ValueError("access_token is required for authorized status")
        elif self.access_token is not None:
            raise ValueError("access_token is only allowed for authorized status")


class GitHubConnectionStartStatus(StrEnum):
    """Результат запуска фоновой GitHub-авторизации."""

    STARTED = "started"  # Новый Device Flow запущен.
    ALREADY_PENDING = "already_pending"  # Для пользователя уже ожидается код.
    PREPARING = "preparing"  # GitHub ещё выдаёт первый Device Flow challenge.


@dataclass(frozen=True, slots=True)
class GitHubConnectionStartResult:
    """Возвращает пользователю installation URL и Device Flow challenge."""

    status: GitHubConnectionStartStatus
    installation_url: str
    authorization: GitHubDeviceAuthorization | None = None


class GitHubGatewayError(RuntimeError):
    """Ошибка безопасного взаимодействия с GitHub authentication API."""
