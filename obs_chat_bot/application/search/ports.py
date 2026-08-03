"""Application ports разбиения vault-заметок на chunks."""

from __future__ import annotations

from typing import Protocol

from obs_chat_bot.application.search.models import (
    ChunkIndexUpdate,
    VaultNoteChunkDraft,
)
from obs_chat_bot.domain.search.entities import (
    VaultChunkIndexState,
    VaultChunkSearchHit,
    VaultNoteChunk,
)
from obs_chat_bot.domain.vaults.entities import VaultNote


class VaultNoteChunker(Protocol):
    """Описывает project-facing разбиение сохранённой vault-заметки."""

    @property
    def index_signature(self) -> str:
        """Возвращает signature алгоритма и policy для будущего индекса."""

    def split(self, note: VaultNote) -> tuple[VaultNoteChunkDraft, ...]:
        """Разбивает сохранённую заметку и добавляет project IDs.

        Args:
            note: Vault-заметка с назначенным SQLite ID.

        Returns:
            Chunks, связанные с пользователем, vault и заметкой.

        Raises:
            ValueError: Если заметка ещё не сохранена и не имеет ID.
        """


class VaultChunkIndexRepository(Protocol):
    """Описывает storage chunks и signature согласованного индекса vault."""

    def get_state(
        self,
        *,
        app_user_id: int,
        vault_id: int,
    ) -> VaultChunkIndexState | None:
        """Возвращает состояние полного индекса либо `None`, если он invalid."""

    def list_for_note(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        note_id: int,
    ) -> list[VaultNoteChunk]:
        """Возвращает chunks заметки в порядке позиции."""

    def list_for_vault(
        self,
        *,
        app_user_id: int,
        vault_id: int,
    ) -> list[VaultNoteChunk]:
        """Возвращает все chunks vault в порядке заметки и позиции."""

    def invalidate(self, *, app_user_id: int, vault_id: int) -> None:
        """Удаляет marker согласованности до потенциально частичной записи."""

    def replace_for_note(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        note_id: int,
        chunks: tuple[VaultNoteChunkDraft, ...],
    ) -> ChunkIndexUpdate:
        """Атомарно приводит chunks одной заметки к переданному набору."""

    def delete_for_notes(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        note_ids: set[int],
    ) -> int:
        """Удаляет chunks перечисленных заметок и возвращает число строк."""

    def replace_for_vault(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        chunks: tuple[VaultNoteChunkDraft, ...],
        index_signature: str,
    ) -> ChunkIndexUpdate:
        """Атомарно перестраивает все chunks и фиксирует новую signature."""

    def mark_current(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        index_signature: str,
    ) -> VaultChunkIndexState:
        """Фиксирует завершение успешного инкрементального обновления."""


class VaultFullTextSearchRepository(Protocol):
    """Описывает точный полнотекстовый поиск по сохранённым chunks vault."""

    def search(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        query: str,
        expected_index_signature: str,
        limit: int,
    ) -> tuple[VaultChunkSearchHit, ...]:
        """Возвращает релевантные chunks только из актуального поколения.

        Args:
            app_user_id: Внутренний ID пользователя приложения.
            vault_id: ID активного Obsidian vault.
            query: Пользовательский текст, а не сырой синтаксис FTS5.
            expected_index_signature: Signature текущих parser и policy.
            limit: Максимальное число результатов.

        Returns:
            Chunks в порядке убывания полнотекстовой релевантности.
        """
