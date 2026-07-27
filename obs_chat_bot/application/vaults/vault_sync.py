from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from obs_chat_bot.application.vaults.github_models import (
    GitHubVaultSnapshotStatus,
)
from obs_chat_bot.application.vaults.markdown import parse_markdown
from obs_chat_bot.application.vaults.ports import (
    GitHubVaultGateway,
    ObsidianVaultRepository,
    VaultNoteRepository,
    VaultSyncLeaseRepository,
)
from obs_chat_bot.domain.vaults.entities import ObsidianVault, VaultNote


class VaultSyncStatus(StrEnum):
    """Описывает итог одной попытки синхронизации."""

    SYNCED = "synced"  # Локальный каталог приведён к удалённому состоянию.
    UNCHANGED = "unchanged"  # Удалённое дерево vault не изменилось.
    IN_PROGRESS = "in_progress"  # Другой процесс уже синхронизирует vault.
    NO_VAULT = "no_vault"  # Пользователь ещё не выбрал vault.


@dataclass(frozen=True, slots=True)
class VaultSyncResult:
    """Содержит итог и счётчики синхронизации vault."""

    status: VaultSyncStatus
    vault: ObsidianVault | None = None
    total_notes: int = 0
    downloaded_notes: int = 0
    added_notes: int = 0
    updated_notes: int = 0
    deleted_notes: int = 0


@dataclass(frozen=True, slots=True)
class VaultStatus:
    """Содержит пользовательский статус локальной копии vault."""

    vault: ObsidianVault | None
    note_count: int = 0


class VaultSyncManager(Protocol):
    """Описывает синхронизацию через безопасные короткие data-соединения."""

    def sync(self, app_user_id: int) -> VaultSyncResult:
        """Синхронизирует активный vault пользователя."""

    def get_status(self, app_user_id: int) -> VaultStatus:
        """Возвращает состояние подключения и число локальных заметок."""


class VaultSyncService:
    """Синхронизирует Markdown vault инкрементально и под lease."""

    def __init__(
        self,
        *,
        vault_repository: ObsidianVaultRepository,
        note_repository: VaultNoteRepository,
        lease_repository: VaultSyncLeaseRepository,
        github_gateway: GitHubVaultGateway,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> None:
        self._vault_repository = vault_repository
        self._note_repository = note_repository
        self._lease_repository = lease_repository
        self._github_gateway = github_gateway
        self._clock = clock
        self._lease_duration = lease_duration

    def sync(self, app_user_id: int) -> VaultSyncResult:
        """Обновляет локальную копию, скачивая только изменённые Markdown blobs."""
        vault = self._vault_repository.get_for_user(app_user_id)
        if vault is None or vault.id is None:
            return VaultSyncResult(status=VaultSyncStatus.NO_VAULT)
        now = self._clock()
        owner = uuid4().hex
        lease = self._lease_repository.acquire(
            app_user_id=app_user_id,
            vault_id=vault.id,
            owner=owner,
            now=now,
            expires_at=now + self._lease_duration,
        )
        if lease is None:
            return VaultSyncResult(
                status=VaultSyncStatus.IN_PROGRESS,
                vault=vault,
            )
        try:
            return self._sync_locked(vault, now=now)
        finally:
            self._lease_repository.release(
                app_user_id=app_user_id,
                vault_id=vault.id,
                owner=owner,
            )

    def get_status(self, app_user_id: int) -> VaultStatus:
        """Возвращает активный vault и размер его локального Markdown-каталога."""
        vault = self._vault_repository.get_for_user(app_user_id)
        if vault is None or vault.id is None:
            return VaultStatus(vault=None)
        notes = self._note_repository.list_for_vault(
            app_user_id=app_user_id,
            vault_id=vault.id,
        )
        return VaultStatus(vault=vault, note_count=len(notes))

    def _sync_locked(
        self,
        vault: ObsidianVault,
        *,
        now: datetime,
    ) -> VaultSyncResult:
        if vault.id is None:
            raise ValueError("vault must be saved before synchronization")
        local_notes = self._note_repository.list_for_vault(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
        )
        local_by_path = {note.path: note for note in local_notes}
        snapshot = self._github_gateway.fetch_vault_snapshot(
            vault,
            known_blobs={
                note.path: note.blob_sha
                for note in local_notes
            },
        )
        if snapshot.status is GitHubVaultSnapshotStatus.NOT_MODIFIED:
            updated = self._update_state(vault, snapshot, now=now, synced=False)
            return VaultSyncResult(
                status=VaultSyncStatus.UNCHANGED,
                vault=updated,
                total_notes=len(local_notes),
            )
        if snapshot.status is GitHubVaultSnapshotStatus.TREE_UNCHANGED:
            updated = self._update_state(vault, snapshot, now=now, synced=False)
            return VaultSyncResult(
                status=VaultSyncStatus.UNCHANGED,
                vault=updated,
                total_notes=len(local_notes),
            )

        remote_paths = {file.path for file in snapshot.files}
        deleted_paths = set(local_by_path) - remote_paths
        pending_notes: list[VaultNote] = []
        added = 0
        updated_count = 0
        for file in snapshot.files:
            local = local_by_path.get(file.path)
            if local is not None and local.blob_sha == file.blob_sha:
                continue
            if file.markdown is None:
                raise RuntimeError("Changed GitHub blob has no Markdown content")
            metadata = parse_markdown(file.path, file.markdown)
            pending_notes.append(
                VaultNote(
                    app_user_id=vault.app_user_id,
                    vault_id=vault.id,
                    path=file.path,
                    blob_sha=file.blob_sha,
                    markdown=file.markdown,
                    title=metadata.title,
                    frontmatter=metadata.frontmatter,
                    tags=metadata.tags,
                    wikilinks=metadata.wikilinks,
                )
            )
            if local is None:
                added += 1
            else:
                updated_count += 1

        # Source SHA фиксируется лишь после успешной записи всех заметок.
        for note in pending_notes:
            self._note_repository.upsert(note)
        deleted = self._note_repository.delete_paths(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
            paths=deleted_paths,
        )
        updated_vault = self._update_state(vault, snapshot, now=now, synced=True)
        return VaultSyncResult(
            status=VaultSyncStatus.SYNCED,
            vault=updated_vault,
            total_notes=len(remote_paths),
            downloaded_notes=len(pending_notes),
            added_notes=added,
            updated_notes=updated_count,
            deleted_notes=deleted,
        )

    def _update_state(self, vault, snapshot, *, now, synced):
        updated = self._vault_repository.update_sync_state(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
            head_commit_sha=snapshot.head_commit_sha,
            tree_sha=snapshot.tree_sha,
            head_etag=snapshot.head_etag,
            last_checked_at=now,
            last_synced_at=now if synced else None,
        )
        if updated is None:
            raise RuntimeError("Synchronized vault could not be read")
        return updated
