from __future__ import annotations

from pathlib import Path

from obs_chat_bot.application.vaults.ports import GitHubVaultGateway
from obs_chat_bot.application.vaults.vault_sync import (
    VaultStatus,
    VaultSyncManager,
    VaultSyncResult,
    VaultSyncService,
)
from obs_chat_bot.data.sqlite.connection import connect_database
from obs_chat_bot.data.sqlite.obsidian_vault_repository import (
    SQLiteObsidianVaultRepository,
)
from obs_chat_bot.data.sqlite.vault_note_repository import SQLiteVaultNoteRepository
from obs_chat_bot.data.sqlite.vault_instruction_repository import (
    SQLiteVaultInstructionRepository,
)
from obs_chat_bot.data.sqlite.vault_sync_lease_repository import (
    SQLiteVaultSyncLeaseRepository,
)


class SQLiteGitHubVaultSyncManager(VaultSyncManager):
    """Собирает синхронизацию vault на отдельном SQLite-соединении."""

    def __init__(
        self,
        *,
        database_path: Path,
        github_gateway: GitHubVaultGateway,
    ) -> None:
        self._database_path = database_path
        self._github_gateway = github_gateway

    def sync(self, app_user_id: int) -> VaultSyncResult:
        """Синхронизирует vault пользователя через GitHub и SQLite."""
        with connect_database(self._database_path) as connection:
            return VaultSyncService(
                vault_repository=SQLiteObsidianVaultRepository(connection),
                note_repository=SQLiteVaultNoteRepository(connection),
                instruction_repository=SQLiteVaultInstructionRepository(connection),
                lease_repository=SQLiteVaultSyncLeaseRepository(connection),
                github_gateway=self._github_gateway,
            ).sync(app_user_id)

    def sync_if_stale(self, app_user_id: int) -> VaultSyncResult:
        """Проверяет vault только после истечения шестичасового окна."""
        with connect_database(self._database_path) as connection:
            return VaultSyncService(
                vault_repository=SQLiteObsidianVaultRepository(connection),
                note_repository=SQLiteVaultNoteRepository(connection),
                instruction_repository=SQLiteVaultInstructionRepository(connection),
                lease_repository=SQLiteVaultSyncLeaseRepository(connection),
                github_gateway=self._github_gateway,
            ).sync_if_stale(app_user_id)

    def get_status(self, app_user_id: int) -> VaultStatus:
        """Возвращает статус локальной копии выбранного vault."""
        with connect_database(self._database_path) as connection:
            return VaultSyncService(
                vault_repository=SQLiteObsidianVaultRepository(connection),
                note_repository=SQLiteVaultNoteRepository(connection),
                instruction_repository=SQLiteVaultInstructionRepository(connection),
                lease_repository=SQLiteVaultSyncLeaseRepository(connection),
                github_gateway=self._github_gateway,
            ).get_status(app_user_id)
