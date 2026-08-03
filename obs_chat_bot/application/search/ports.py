"""Application ports разбиения vault-заметок на chunks."""

from __future__ import annotations

from typing import Protocol

from obs_chat_bot.application.search.models import VaultNoteChunkDraft
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
