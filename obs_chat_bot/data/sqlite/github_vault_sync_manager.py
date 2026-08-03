from __future__ import annotations

from pathlib import Path
import sqlite3

from obs_chat_bot.application.search.indexing import VaultChunkIndexer
from obs_chat_bot.application.search.ports import VaultNoteChunker
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
from obs_chat_bot.data.sqlite.vault_chunk_index_repository import (
    SQLiteVaultChunkIndexRepository,
)
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
        note_chunker: VaultNoteChunker,
    ) -> None:
        self._database_path = database_path
        self._github_gateway = github_gateway
        self._note_chunker = note_chunker

    def _create_service(self, connection: sqlite3.Connection) -> VaultSyncService:
        """Собирает sync service и chunk index на одном SQLite-соединении."""
        return VaultSyncService(
            vault_repository=SQLiteObsidianVaultRepository(connection),
            note_repository=SQLiteVaultNoteRepository(connection),
            instruction_repository=SQLiteVaultInstructionRepository(connection),
            lease_repository=SQLiteVaultSyncLeaseRepository(connection),
            github_gateway=self._github_gateway,
            chunk_indexer=VaultChunkIndexer(
                chunker=self._note_chunker,
                repository=SQLiteVaultChunkIndexRepository(connection),
            ),
        )

    def sync(self, app_user_id: int) -> VaultSyncResult:
        """Синхронизирует vault пользователя через GitHub и SQLite."""
        with connect_database(self._database_path) as connection:
            return self._create_service(connection).sync(app_user_id)

    def sync_if_stale(self, app_user_id: int) -> VaultSyncResult:
        """Проверяет vault только после истечения шестичасового окна."""
        with connect_database(self._database_path) as connection:
            return self._create_service(connection).sync_if_stale(app_user_id)

    def get_status(self, app_user_id: int) -> VaultStatus:
        """Возвращает статус локальной копии выбранного vault."""
        with connect_database(self._database_path) as connection:
            return self._create_service(connection).get_status(app_user_id)
