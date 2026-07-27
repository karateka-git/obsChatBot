"""Тесты application-сервиса инкрементальной синхронизации vault."""

from datetime import UTC, datetime
import unittest

from obs_chat_bot.application.vaults.github_models import (
    GitHubMarkdownFile,
    GitHubVaultSnapshot,
    GitHubVaultSnapshotStatus,
)
from obs_chat_bot.application.vaults.vault_sync import (
    VaultSyncService,
    VaultSyncStatus,
)
from obs_chat_bot.domain.vaults.entities import ObsidianVault, VaultNote, VaultSyncLease


NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class MemoryVaultRepository:
    """Минимальное хранилище vault для unit-теста."""

    def __init__(self, vault):
        self.vault = vault
        self.updates = []

    def get_for_user(self, _app_user_id):
        return self.vault

    def update_sync_state(self, **values):
        self.updates.append(values)
        self.vault = ObsidianVault(
            app_user_id=self.vault.app_user_id,
            installation_id=self.vault.installation_id,
            repository_id=self.vault.repository_id,
            owner=self.vault.owner,
            repository=self.vault.repository,
            branch=self.vault.branch,
            id=self.vault.id,
            head_commit_sha=values["head_commit_sha"] or self.vault.head_commit_sha,
            tree_sha=values["tree_sha"] or self.vault.tree_sha,
            head_etag=values["head_etag"] or self.vault.head_etag,
            last_checked_at=values["last_checked_at"],
            last_synced_at=values["last_synced_at"] or self.vault.last_synced_at,
        )
        return self.vault


class MemoryNoteRepository:
    """Минимальное хранилище заметок для unit-теста."""

    def __init__(self, notes):
        self.notes = {note.path: note for note in notes}

    def list_for_vault(self, **_values):
        return sorted(self.notes.values(), key=lambda note: note.path)

    def upsert(self, note):
        self.notes[note.path] = note
        return note

    def delete_paths(self, *, paths, **_values):
        deleted = 0
        for path in paths:
            deleted += self.notes.pop(path, None) is not None
        return deleted


class MemoryLeaseRepository:
    """Всегда выдаёт свободный lease и фиксирует освобождение."""

    def __init__(self):
        self.released = False

    def acquire(self, **values):
        return VaultSyncLease(
            app_user_id=values["app_user_id"],
            vault_id=values["vault_id"],
            owner=values["owner"],
            acquired_at=values["now"],
            expires_at=values["expires_at"],
        )

    def release(self, **_values):
        self.released = True
        return True


class FailingNoteRepository(MemoryNoteRepository):
    """Имитирует сбой SQLite при сохранении изменённой заметки."""

    def upsert(self, note):
        raise RuntimeError("storage failed")


class SnapshotGateway:
    """Возвращает заранее подготовленный снимок и запоминает manifest."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.known_blobs = None

    def fetch_vault_snapshot(self, _vault, *, known_blobs):
        self.known_blobs = known_blobs
        return self.snapshot


class VaultSyncTest(unittest.TestCase):
    """Проверяет добавление, изменение, удаление и фиксацию source SHA."""

    def test_sync_applies_changed_manifest_and_metadata(self) -> None:
        """Сервис скачанные blobs upsert-ит, а отсутствующие пути удаляет."""
        vault = _vault()
        old = VaultNote(
            app_user_id=1,
            vault_id=10,
            path="old.md",
            blob_sha="old-sha",
            markdown="old",
        )
        notes = MemoryNoteRepository([old])
        gateway = SnapshotGateway(
            GitHubVaultSnapshot(
                status=GitHubVaultSnapshotStatus.CHANGED,
                head_commit_sha="commit-2",
                tree_sha="tree-2",
                head_etag='"etag-2"',
                files=(
                    GitHubMarkdownFile(
                        path="new.md",
                        blob_sha="new-sha",
                        markdown="---\ntags: [one, two]\n---\n# New\n[[Old]]",
                    ),
                ),
            )
        )
        vaults = MemoryVaultRepository(vault)
        leases = MemoryLeaseRepository()

        result = VaultSyncService(
            vault_repository=vaults,
            note_repository=notes,
            lease_repository=leases,
            github_gateway=gateway,
            clock=lambda: NOW,
        ).sync(1)

        self.assertEqual(result.status, VaultSyncStatus.SYNCED)
        self.assertEqual((result.added_notes, result.deleted_notes), (1, 1))
        self.assertEqual(gateway.known_blobs, {"old.md": "old-sha"})
        self.assertEqual(notes.notes["new.md"].tags, ("one", "two"))
        self.assertEqual(notes.notes["new.md"].wikilinks, ("Old",))
        self.assertEqual(vaults.vault.tree_sha, "tree-2")
        self.assertEqual(vaults.vault.last_synced_at, NOW)
        self.assertTrue(leases.released)

    def test_not_modified_only_advances_check_time(self) -> None:
        """HTTP 304 не меняет source SHA и не выполняет повторную запись."""
        vaults = MemoryVaultRepository(_vault())
        result = VaultSyncService(
            vault_repository=vaults,
            note_repository=MemoryNoteRepository([]),
            lease_repository=MemoryLeaseRepository(),
            github_gateway=SnapshotGateway(
                GitHubVaultSnapshot(
                    status=GitHubVaultSnapshotStatus.NOT_MODIFIED,
                    head_etag='"etag-1"',
                )
            ),
            clock=lambda: NOW,
        ).sync(1)

        self.assertEqual(result.status, VaultSyncStatus.UNCHANGED)
        self.assertEqual(vaults.vault.head_commit_sha, "commit-1")
        self.assertIsNone(vaults.vault.last_synced_at)
        self.assertEqual(vaults.vault.last_checked_at, NOW)

    def test_storage_failure_does_not_advance_source_sha(self) -> None:
        """Новый source SHA не фиксируется после неполной локальной записи."""
        vaults = MemoryVaultRepository(_vault())
        leases = MemoryLeaseRepository()
        service = VaultSyncService(
            vault_repository=vaults,
            note_repository=FailingNoteRepository([]),
            lease_repository=leases,
            github_gateway=SnapshotGateway(
                GitHubVaultSnapshot(
                    status=GitHubVaultSnapshotStatus.CHANGED,
                    head_commit_sha="commit-2",
                    tree_sha="tree-2",
                    files=(
                        GitHubMarkdownFile(
                            path="new.md",
                            blob_sha="new-sha",
                            markdown="# New",
                        ),
                    ),
                )
            ),
            clock=lambda: NOW,
        )

        with self.assertRaisesRegex(RuntimeError, "storage failed"):
            service.sync(1)

        self.assertEqual(vaults.updates, [])
        self.assertEqual(vaults.vault.head_commit_sha, "commit-1")
        self.assertTrue(leases.released)


def _vault():
    return ObsidianVault(
        id=10,
        app_user_id=1,
        installation_id=20,
        repository_id=30,
        owner="owner",
        repository="notes",
        branch="main",
        head_commit_sha="commit-1",
        tree_sha="tree-1",
        head_etag='"etag-1"',
    )


if __name__ == "__main__":
    unittest.main()
