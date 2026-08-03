"""Application-сервис инкрементальной индексации Markdown chunks."""

from __future__ import annotations

from obs_chat_bot.application.search.models import ChunkIndexUpdate
from obs_chat_bot.application.search.ports import (
    VaultChunkIndexRepository,
    VaultNoteChunker,
)
from obs_chat_bot.domain.vaults.entities import VaultNote


class VaultChunkIndexer:
    """Координирует chunker и storage без знания SQLite или GitHub."""

    def __init__(
        self,
        *,
        chunker: VaultNoteChunker,
        repository: VaultChunkIndexRepository,
    ) -> None:
        self._chunker = chunker
        self._repository = repository

    @property
    def index_signature(self) -> str:
        """Возвращает текущую signature parser, engine и policy."""
        return self._chunker.index_signature

    def is_current(self, *, app_user_id: int, vault_id: int) -> bool:
        """Проверяет, соответствует ли полный индекс текущей signature."""
        state = self._repository.get_state(
            app_user_id=app_user_id,
            vault_id=vault_id,
        )
        return (
            state is not None
            and state.index_signature == self.index_signature
        )

    def invalidate(self, *, app_user_id: int, vault_id: int) -> None:
        """Помечает индекс несогласованным до начала связанных записей."""
        self._repository.invalidate(app_user_id=app_user_id, vault_id=vault_id)

    def index_note(self, note: VaultNote) -> ChunkIndexUpdate:
        """Перестраивает только chunks одной уже сохранённой заметки."""
        if note.id is None:
            raise ValueError("note must be saved before indexing")
        chunks = self._chunker.split(note)
        return self._repository.replace_for_note(
            app_user_id=note.app_user_id,
            vault_id=note.vault_id,
            note_id=note.id,
            chunks=chunks,
        )

    def delete_notes(self, notes: tuple[VaultNote, ...]) -> int:
        """Удаляет chunks заметок перед каскадным удалением source rows."""
        if not notes:
            return 0
        app_user_id = notes[0].app_user_id
        vault_id = notes[0].vault_id
        note_ids: set[int] = set()
        for note in notes:
            if note.id is None:
                raise ValueError("note must be saved before deleting its chunks")
            if note.app_user_id != app_user_id or note.vault_id != vault_id:
                raise ValueError("all notes must belong to one user and vault")
            note_ids.add(note.id)
        return self._repository.delete_for_notes(
            app_user_id=app_user_id,
            vault_id=vault_id,
            note_ids=note_ids,
        )

    def rebuild(
        self,
        *,
        app_user_id: int,
        vault_id: int,
        notes: tuple[VaultNote, ...],
    ) -> ChunkIndexUpdate:
        """Полностью перестраивает vault при новой или изменённой signature."""
        chunks = []
        for note in notes:
            if note.app_user_id != app_user_id or note.vault_id != vault_id:
                raise ValueError("all notes must belong to requested user and vault")
            chunks.extend(self._chunker.split(note))
        return self._repository.replace_for_vault(
            app_user_id=app_user_id,
            vault_id=vault_id,
            chunks=tuple(chunks),
            index_signature=self.index_signature,
        )

    def mark_current(self, *, app_user_id: int, vault_id: int) -> None:
        """Фиксирует успешное завершение всех инкрементальных операций."""
        self._repository.mark_current(
            app_user_id=app_user_id,
            vault_id=vault_id,
            index_signature=self.index_signature,
        )
