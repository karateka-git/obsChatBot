from __future__ import annotations

from datetime import datetime
from typing import Protocol

from obs_chat_bot.application.vaults.github_models import (
    GitHubAuthenticatedAccount,
    GitHubConnectionCompletion,
    GitHubConnectionStartResult,
    GitHubDeviceAuthorization,
    GitHubDevicePollResult,
    GitHubInstallationAccessToken,
    GitHubRepositoryInspection,
    GitHubUserAccessToken,
)

from obs_chat_bot.domain.vaults.entities import (
    GitHubAccount,
    GitHubReconnectConfirmation,
    GitHubInstallation,
    ObsidianVault,
    VaultActionConfirmation,
    VaultNote,
    VaultSyncLease,
)


class GitHubInstallationRepository(Protocol):
    """Описывает хранение разрешённых пользователю установок GitHub App."""

    def replace_for_user(
        self,
        *,
        app_user_id: int,
        installation_ids: set[int],
    ) -> list[GitHubInstallation]:
        """Синхронизирует разрешённые installation IDs пользователя."""

    def list_for_user(self, app_user_id: int) -> list[GitHubInstallation]:
        """Возвращает разрешённые установки пользователя."""

    def contains(self, *, app_user_id: int, installation_id: int) -> bool:
        """Проверяет доступ пользователя к установке GitHub App."""

    def delete_for_user(self, app_user_id: int) -> None:
        """Удаляет все разрешённые установки пользователя."""


class ObsidianVaultRepository(Protocol):
    """Описывает хранение единственного активного vault пользователя."""

    def create_if_absent(self, vault: ObsidianVault) -> ObsidianVault | None:
        """Создаёт первый vault атомарно или возвращает `None` при конфликте."""

    def replace(self, vault: ObsidianVault) -> ObsidianVault:
        """Заменяет активный vault и удаляет данные предыдущего подключения."""

    def get_by_id(
        self,
        *,
        app_user_id: int,
        vault_id: int,
    ) -> ObsidianVault | None:
        """Возвращает vault по ID внутри области пользователя."""

    def get_for_user(self, app_user_id: int) -> ObsidianVault | None:
        """Возвращает активный vault пользователя или `None`."""

    def update_sync_state(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        head_commit_sha: str | None,
        tree_sha: str | None,
        head_etag: str | None,
        last_checked_at: datetime,
        last_synced_at: datetime | None,
    ) -> ObsidianVault | None:
        """Обновляет зафиксированное состояние источника после проверки."""

    def delete_for_user(self, app_user_id: int) -> None:
        """Удаляет активный vault пользователя и зависимые локальные данные."""


class VaultNoteRepository(Protocol):
    """Описывает хранение Markdown-заметок подключённого vault."""

    def upsert(self, note: VaultNote) -> VaultNote:
        """Создаёт или атомарно обновляет заметку и её metadata."""

    def get_by_path(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        path: str,
    ) -> VaultNote | None:
        """Возвращает заметку по пути внутри vault пользователя."""

    def list_for_vault(
        self,
        *,
        app_user_id: int,
        vault_id: int,
    ) -> list[VaultNote]:
        """Возвращает все заметки vault в порядке пути."""

    def delete_paths(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        paths: set[str],
    ) -> int:
        """Удаляет перечисленные заметки и возвращает число удалённых строк."""


class VaultSyncLeaseRepository(Protocol):
    """Описывает межпроцессный lease синхронизации vault."""

    def acquire(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        owner: str,
        now: datetime,
        expires_at: datetime,
    ) -> VaultSyncLease | None:
        """Захватывает свободный или истёкший lease, иначе возвращает `None`."""

    def get(
        self,
        *,
        app_user_id: int,
        vault_id: int,
    ) -> VaultSyncLease | None:
        """Возвращает текущий lease vault или `None`."""

    def release(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        owner: str,
    ) -> bool:
        """Освобождает lease только для захватившего его владельца."""


class VaultActionConfirmationRepository(Protocol):
    """Описывает хранение подтверждений замены и отключения vault."""

    def save(self, confirmation: VaultActionConfirmation) -> None:
        """Сохраняет подтверждение, заменяя предыдущее действие пользователя."""

    def find_active(
        self,
        *,
        app_user_id: int,
        now: datetime,
    ) -> VaultActionConfirmation | None:
        """Возвращает неистёкшее подтверждение пользователя или `None`."""

    def delete(self, app_user_id: int) -> None:
        """Удаляет ожидающее подтверждение пользователя."""


class GitHubDeviceFlowGateway(Protocol):
    """Описывает внешние операции GitHub Device Flow."""

    def request_device_authorization(self) -> GitHubDeviceAuthorization:
        """Запрашивает новый Device Flow challenge у GitHub."""

    def poll_device_token(self, device_code: str) -> GitHubDevicePollResult:
        """Выполняет одну проверку состояния Device Flow."""

    def list_installation_ids(
        self,
        access_token: GitHubUserAccessToken,
    ) -> set[int]:
        """Возвращает installation IDs, доступные авторизованному пользователю."""

    def get_authenticated_account(
        self,
        access_token: GitHubUserAccessToken,
    ) -> GitHubAuthenticatedAccount:
        """Возвращает публичные ID и login авторизованного GitHub-аккаунта."""


class GitHubInstallationTokenProvider(Protocol):
    """Описывает выпуск краткоживущего installation access token."""

    def create_installation_token(
        self,
        *,
        installation_id: int,
        repository_id: int | None = None,
    ) -> GitHubInstallationAccessToken:
        """Создаёт token установки, при необходимости ограниченный одним repo."""


class GitHubRepositoryGateway(Protocol):
    """Проверяет право записи repository и читает каталог vault через GitHub App."""

    def inspect_repository(
        self,
        *,
        installation_id: int,
        owner: str,
        repository: str,
        root_path: str,
    ) -> GitHubRepositoryInspection | None:
        """Возвращает inspection или `None` без фактического `Contents: write`."""


class GitHubAccountAccessWriter(Protocol):
    """Описывает потокобезопасную замену GitHub-аккаунта и его доступов."""

    def replace_for_user(
        self,
        *,
        app_user_id: int,
        github_user_id: int,
        login: str,
        installation_ids: set[int],
    ) -> None:
        """Атомарно сохраняет аккаунт и актуальные installation IDs."""


class GitHubConnectionStateStore(Protocol):
    """Хранит безопасное межпроцессное состояние подключения GitHub."""

    def get_account(self, app_user_id: int) -> GitHubAccount | None:
        """Возвращает подключённый GitHub-аккаунт пользователя."""

    def request_reconnect(
        self,
        *,
        app_user_id: int,
        account_login: str,
        expires_at: datetime,
    ) -> None:
        """Сохраняет ожидающее подтверждение замены аккаунта."""

    def find_reconnect_confirmation(
        self,
        *,
        app_user_id: int,
        now: datetime,
    ) -> GitHubReconnectConfirmation | None:
        """Возвращает активное подтверждение или удаляет истёкшее."""

    def delete_reconnect_confirmation(self, app_user_id: int) -> None:
        """Удаляет ожидающее подтверждение переподключения."""

    def acquire_attempt(
        self,
        *,
        app_user_id: int,
        owner: str,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        """Захватывает claim запуска Device Flow между процессами."""

    def has_active_attempt(self, *, app_user_id: int, now: datetime) -> bool:
        """Проверяет наличие незавершённого Device Flow в любом процессе."""

    def release_attempt(self, *, app_user_id: int, owner: str) -> None:
        """Освобождает claim только его владельцем."""


class GitHubConnectionCompletionHandler(Protocol):
    """Принимает безопасный итог фоновой GitHub-авторизации."""

    def __call__(self, completion: GitHubConnectionCompletion) -> None:
        """Передаёт итог presentation-слою для отправки пользователю."""


class GitHubConnectionStarter(Protocol):
    """Описывает запуск фоновой авторизации из общего incoming-flow."""

    def start(
        self,
        app_user_id: int,
        completion_handler: GitHubConnectionCompletionHandler | None = None,
    ) -> GitHubConnectionStartResult:
        """Запускает Device Flow или возвращает уже ожидающий challenge."""

    def has_reconnect_confirmation(self, app_user_id: int) -> bool:
        """Проверяет ожидание ответа `да`/`нет` на замену аккаунта."""

    def confirm_reconnect(
        self,
        app_user_id: int,
        completion_handler: GitHubConnectionCompletionHandler | None = None,
    ) -> GitHubConnectionStartResult | None:
        """Подтверждает замену и запускает новый Device Flow."""

    def cancel_reconnect(self, app_user_id: int) -> bool:
        """Отменяет ожидающую замену GitHub-аккаунта."""
