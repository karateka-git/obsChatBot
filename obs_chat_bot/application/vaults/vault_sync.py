from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import logging
import time
from typing import Protocol
from uuid import uuid4

from obs_chat_bot.application.search.indexing import VaultChunkIndexer
from obs_chat_bot.application.search.models import ChunkIndexUpdate
from obs_chat_bot.application.vaults.github_models import (
    GitHubVaultSnapshotStatus,
)
from obs_chat_bot.application.vaults.markdown import parse_markdown
from obs_chat_bot.application.vaults.ports import (
    GitHubVaultGateway,
    ObsidianVaultRepository,
    VaultInstructionRepository,
    VaultNoteRepository,
    VaultSyncLeaseRepository,
)
from obs_chat_bot.domain.vaults.entities import (
    ObsidianVault,
    VaultInstruction,
    VaultNote,
)


DEFAULT_AUTO_SYNC_INTERVAL = timedelta(hours=6)
LOGGER = logging.getLogger(__name__)


class VaultSyncStatus(StrEnum):
    """Описывает итог одной попытки синхронизации."""

    SYNCED = "synced"  # Локальный каталог приведён к удалённому состоянию.
    UNCHANGED = "unchanged"  # Удалённое дерево vault не изменилось.
    IN_PROGRESS = "in_progress"  # Другой процесс уже синхронизирует vault.
    NO_VAULT = "no_vault"  # Пользователь ещё не выбрал vault.
    FRESH = "fresh"  # Недавняя проверка позволяет не обращаться к GitHub.


class VaultSyncWarningReason(StrEnum):
    """Причина использования последней локальной копии vault."""

    UPDATE_FAILED = "update_failed"  # Автоматическое обновление завершилось ошибкой.
    IN_PROGRESS = "in_progress"  # Vault синхронизируется в другом процессе.


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
    instruction_files: int = 0
    created_chunks: int = 0
    updated_chunks: int = 0
    deleted_chunks: int = 0
    unchanged_chunks: int = 0
    index_rebuilt: bool = False


@dataclass(frozen=True, slots=True)
class VaultSyncWarning:
    """Описывает безопасный fallback на последнюю локальную копию."""

    reason: VaultSyncWarningReason
    note_count: int = 0
    last_checked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason, VaultSyncWarningReason):
            raise TypeError("reason must be a VaultSyncWarningReason")
        if self.note_count < 0:
            raise ValueError("note_count must not be negative")


@dataclass(frozen=True, slots=True)
class VaultStatus:
    """Содержит пользовательский статус локальной копии vault."""

    vault: ObsidianVault | None
    note_count: int = 0
    instruction_count: int = 0


class VaultSyncManager(Protocol):
    """Описывает синхронизацию через безопасные короткие data-соединения."""

    def sync(self, app_user_id: int) -> VaultSyncResult:
        """Синхронизирует активный vault пользователя."""

    def sync_if_stale(self, app_user_id: int) -> VaultSyncResult:
        """Синхронизирует vault, только если шестичасовое окно истекло."""

    def get_status(self, app_user_id: int) -> VaultStatus:
        """Возвращает состояние подключения и число локальных заметок."""


class VaultSyncService:
    """Синхронизирует Markdown vault инкрементально и под lease."""

    def __init__(
        self,
        *,
        vault_repository: ObsidianVaultRepository,
        note_repository: VaultNoteRepository,
        instruction_repository: VaultInstructionRepository,
        lease_repository: VaultSyncLeaseRepository,
        github_gateway: GitHubVaultGateway,
        chunk_indexer: VaultChunkIndexer,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> None:
        self._vault_repository = vault_repository
        self._note_repository = note_repository
        self._instruction_repository = instruction_repository
        self._lease_repository = lease_repository
        self._github_gateway = github_gateway
        self._chunk_indexer = chunk_indexer
        self._clock = clock
        self._lease_duration = lease_duration

    def sync(self, app_user_id: int) -> VaultSyncResult:
        """Обновляет локальную копию, скачивая только изменённые Markdown blobs."""
        vault = self._vault_repository.get_for_user(app_user_id)
        if vault is None or vault.id is None:
            return VaultSyncResult(status=VaultSyncStatus.NO_VAULT)
        now = self._clock()
        return self._sync_vault(vault, now=now)

    def sync_if_stale(
        self,
        app_user_id: int,
        *,
        max_age: timedelta = DEFAULT_AUTO_SYNC_INTERVAL,
    ) -> VaultSyncResult:
        """Проверяет vault лишь после истечения допустимого возраста копии.

        Args:
            app_user_id: Внутренний ID пользователя приложения.
            max_age: Время, в течение которого последняя проверка считается
                актуальной.

        Returns:
            `FRESH` без GitHub-запроса либо результат обычной синхронизации.

        Raises:
            ValueError: `app_user_id` или `max_age` имеют некорректное значение.
        """
        if app_user_id <= 0:
            raise ValueError("app_user_id must be positive")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        vault = self._vault_repository.get_for_user(app_user_id)
        if vault is None or vault.id is None:
            return VaultSyncResult(status=VaultSyncStatus.NO_VAULT)
        now = self._clock()
        if (
            vault.last_checked_at is not None
            and now - vault.last_checked_at < max_age
        ):
            if not self._chunk_indexer.is_current(
                app_user_id=app_user_id,
                vault_id=vault.id,
            ):
                return self._run_with_lease(
                    vault,
                    now=now,
                    operation=lambda: self._rebuild_local_index(
                        vault,
                        status=VaultSyncStatus.FRESH,
                    ),
                )
            notes = self._note_repository.list_for_vault(
                app_user_id=app_user_id,
                vault_id=vault.id,
            )
            return VaultSyncResult(
                status=VaultSyncStatus.FRESH,
                vault=vault,
                total_notes=len(notes),
            )
        return self._sync_vault(vault, now=now)

    def _sync_vault(
        self,
        vault: ObsidianVault,
        *,
        now: datetime,
    ) -> VaultSyncResult:
        """Захватывает lease и синхронизирует уже найденный vault."""
        if vault.id is None:
            raise ValueError("vault must be saved before synchronization")
        return self._run_with_lease(
            vault,
            now=now,
            operation=lambda: self._sync_locked(vault, now=now),
        )

    def _run_with_lease(
        self,
        vault: ObsidianVault,
        *,
        now: datetime,
        operation: Callable[[], VaultSyncResult],
    ) -> VaultSyncResult:
        """Выполняет локальную или GitHub-синхронизацию под общим lease."""
        if vault.id is None:
            raise ValueError("vault must be saved before synchronization")
        owner = uuid4().hex
        lease = self._lease_repository.acquire(
            app_user_id=vault.app_user_id,
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
            return operation()
        finally:
            self._lease_repository.release(
                app_user_id=vault.app_user_id,
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
        instructions = self._instruction_repository.list_for_vault(
            app_user_id=app_user_id,
            vault_id=vault.id,
        )
        return VaultStatus(
            vault=vault,
            note_count=len(notes),
            instruction_count=len(instructions),
        )

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
        local_instructions = self._instruction_repository.list_for_vault(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
        )
        local_instructions_by_path = {
            instruction.path: instruction
            for instruction in local_instructions
        }
        index_current = self._chunk_indexer.is_current(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
        )
        github_started_at = time.monotonic()
        LOGGER.info(
            "GitHub vault snapshot fetch started: app_user_id=%s vault_id=%s "
            "repository=%s/%s",
            vault.app_user_id,
            vault.id,
            vault.owner,
            vault.repository,
        )
        try:
            snapshot = self._github_gateway.fetch_vault_snapshot(
                vault,
                known_blobs={
                    note.path: note.blob_sha
                    for note in local_notes
                },
                known_instruction_blobs={
                    instruction.path: instruction.blob_sha
                    for instruction in local_instructions
                },
            )
        except Exception:
            LOGGER.exception(
                "GitHub vault snapshot fetch failed: app_user_id=%s "
                "vault_id=%s duration_seconds=%.3f",
                vault.app_user_id,
                vault.id,
                time.monotonic() - github_started_at,
            )
            raise
        LOGGER.info(
            "GitHub vault snapshot fetch completed: app_user_id=%s "
            "vault_id=%s status=%s duration_seconds=%.3f",
            vault.app_user_id,
            vault.id,
            snapshot.status.value,
            time.monotonic() - github_started_at,
        )
        if snapshot.status is GitHubVaultSnapshotStatus.NOT_MODIFIED:
            chunk_update = self._ensure_current_index(
                vault,
                local_notes=tuple(local_notes),
                index_current=index_current,
            )
            updated = self._update_state(vault, snapshot, now=now, synced=False)
            return VaultSyncResult(
                status=VaultSyncStatus.UNCHANGED,
                vault=updated,
                total_notes=len(local_notes),
                instruction_files=len(local_instructions),
                **_chunk_result_fields(chunk_update, rebuilt=not index_current),
            )
        if snapshot.status is GitHubVaultSnapshotStatus.TREE_UNCHANGED:
            chunk_update = self._ensure_current_index(
                vault,
                local_notes=tuple(local_notes),
                index_current=index_current,
            )
            updated = self._update_state(vault, snapshot, now=now, synced=False)
            return VaultSyncResult(
                status=VaultSyncStatus.UNCHANGED,
                vault=updated,
                total_notes=len(local_notes),
                instruction_files=len(local_instructions),
                **_chunk_result_fields(chunk_update, rebuilt=not index_current),
            )

        pending_instructions: list[VaultInstruction] = []
        for file in snapshot.instructions:
            local = local_instructions_by_path.get(file.path)
            content = (
                local.content
                if local is not None and local.blob_sha == file.blob_sha
                else file.content
            )
            if content is None:
                raise RuntimeError("Changed instruction blob has no content")
            pending_instructions.append(
                VaultInstruction(
                    app_user_id=vault.app_user_id,
                    vault_id=vault.id,
                    position=file.position,
                    path=file.path,
                    blob_sha=file.blob_sha,
                    content=content,
                )
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

        sqlite_started_at = time.monotonic()
        LOGGER.info(
            "Vault SQLite write started: app_user_id=%s vault_id=%s "
            "upsert_count=%s delete_count=%s instruction_count=%s",
            vault.app_user_id,
            vault.id,
            len(pending_notes),
            len(deleted_paths),
            len(pending_instructions),
        )
        try:
            requires_index_write = (
                bool(pending_notes or deleted_paths) or not index_current
            )
            if requires_index_write:
                # Marker удаляется до серии отдельных транзакций. При любом сбое
                # следующий запуск безопасно выполнит полный локальный rebuild.
                self._chunk_indexer.invalidate(
                    app_user_id=vault.app_user_id,
                    vault_id=vault.id,
                )
            self._instruction_repository.replace_for_vault(
                app_user_id=vault.app_user_id,
                vault_id=vault.id,
                instructions=tuple(pending_instructions),
            )
            chunk_update = ChunkIndexUpdate()
            for note in pending_notes:
                saved_note = self._note_repository.upsert(note)
                if index_current:
                    chunk_update = chunk_update.merge(
                        self._chunk_indexer.index_note(saved_note)
                    )
            deleted_notes = tuple(
                local_by_path[path]
                for path in sorted(deleted_paths)
            )
            if index_current:
                chunk_update = chunk_update.merge(
                    ChunkIndexUpdate(
                        deleted=self._chunk_indexer.delete_notes(deleted_notes)
                    )
                )
            deleted = self._note_repository.delete_paths(
                app_user_id=vault.app_user_id,
                vault_id=vault.id,
                paths=deleted_paths,
            )
            if not index_current:
                final_notes = self._note_repository.list_for_vault(
                    app_user_id=vault.app_user_id,
                    vault_id=vault.id,
                )
                chunk_update = self._rebuild_index(
                    vault,
                    notes=tuple(final_notes),
                )
            elif requires_index_write:
                self._chunk_indexer.mark_current(
                    app_user_id=vault.app_user_id,
                    vault_id=vault.id,
                )
            # Source SHA фиксируется только после успешной записи всех данных.
            updated_vault = self._update_state(vault, snapshot, now=now, synced=True)
        except Exception:
            LOGGER.exception(
                "Vault SQLite write failed: app_user_id=%s vault_id=%s "
                "duration_seconds=%.3f",
                vault.app_user_id,
                vault.id,
                time.monotonic() - sqlite_started_at,
            )
            raise
        LOGGER.info(
            "Vault SQLite write completed: app_user_id=%s vault_id=%s "
            "duration_seconds=%.3f",
            vault.app_user_id,
            vault.id,
            time.monotonic() - sqlite_started_at,
        )
        return VaultSyncResult(
            status=VaultSyncStatus.SYNCED,
            vault=updated_vault,
            total_notes=len(remote_paths),
            downloaded_notes=len(pending_notes),
            added_notes=added,
            updated_notes=updated_count,
            deleted_notes=deleted,
            instruction_files=len(pending_instructions),
            **_chunk_result_fields(chunk_update, rebuilt=not index_current),
        )

    def _ensure_current_index(
        self,
        vault: ObsidianVault,
        *,
        local_notes: tuple[VaultNote, ...],
        index_current: bool,
    ) -> ChunkIndexUpdate:
        """Перестраивает stale index при неизменившемся GitHub tree."""
        if index_current:
            return ChunkIndexUpdate()
        return self._rebuild_index(vault, notes=local_notes)

    def _rebuild_local_index(
        self,
        vault: ObsidianVault,
        *,
        status: VaultSyncStatus,
    ) -> VaultSyncResult:
        """Обновляет только chunks, не выполняя лишний запрос к GitHub."""
        if vault.id is None:
            raise ValueError("vault must be saved before indexing")
        notes = self._note_repository.list_for_vault(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
        )
        update = self._rebuild_index(vault, notes=tuple(notes))
        instructions = self._instruction_repository.list_for_vault(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
        )
        return VaultSyncResult(
            status=status,
            vault=vault,
            total_notes=len(notes),
            instruction_files=len(instructions),
            **_chunk_result_fields(update, rebuilt=True),
        )

    def _rebuild_index(
        self,
        vault: ObsidianVault,
        *,
        notes: tuple[VaultNote, ...],
    ) -> ChunkIndexUpdate:
        """Атомарно заменяет полное поколение chunks текущей signature."""
        if vault.id is None:
            raise ValueError("vault must be saved before indexing")
        started_at = time.monotonic()
        LOGGER.info(
            "Vault chunk index rebuild started: app_user_id=%s vault_id=%s "
            "note_count=%s index_signature=%s",
            vault.app_user_id,
            vault.id,
            len(notes),
            self._chunk_indexer.index_signature,
        )
        self._chunk_indexer.invalidate(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
        )
        update = self._chunk_indexer.rebuild(
            app_user_id=vault.app_user_id,
            vault_id=vault.id,
            notes=notes,
        )
        LOGGER.info(
            "Vault chunk index rebuild completed: app_user_id=%s vault_id=%s "
            "chunk_count=%s duration_seconds=%.3f",
            vault.app_user_id,
            vault.id,
            update.created,
            time.monotonic() - started_at,
        )
        return update

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


def _chunk_result_fields(
    update: ChunkIndexUpdate,
    *,
    rebuilt: bool,
) -> dict[str, int | bool]:
    """Преобразует внутренние счётчики индекса в поля результата sync."""
    return {
        "created_chunks": update.created,
        "updated_chunks": update.updated,
        "deleted_chunks": update.deleted,
        "unchanged_chunks": update.unchanged,
        "index_rebuilt": rebuilt,
    }
