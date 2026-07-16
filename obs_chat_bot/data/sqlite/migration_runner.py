from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).with_name("migrations")
MIGRATION_NAME_PATTERN = re.compile(r"^(?P<version>\d{4})_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    """Raised when database migrations cannot be discovered or applied."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def apply_migrations(
    connection: sqlite3.Connection,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[Migration]:
    migrations = _discover_migrations(migrations_dir)
    _ensure_migrations_table(connection)
    applied = _get_applied_migrations(connection)
    completed: list[Migration] = []

    for migration in migrations:
        applied_name = applied.get(migration.version)
        if applied_name is not None:
            if applied_name != migration.name:
                raise MigrationError(
                    f"Migration version {migration.version:04d} is already recorded "
                    f"as {applied_name}, not {migration.name}"
                )
            continue

        _apply_migration(connection, migration)
        completed.append(migration)

    return completed


def _discover_migrations(migrations_dir: Path) -> list[Migration]:
    if not migrations_dir.is_dir():
        raise MigrationError(f"Migrations directory does not exist: {migrations_dir}")

    migrations: list[Migration] = []
    versions: set[int] = set()

    for path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_NAME_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"Invalid migration file name: {path.name}")

        version = int(match.group("version"))
        if version in versions:
            raise MigrationError(f"Duplicate migration version: {version:04d}")

        versions.add(version)
        migrations.append(Migration(version=version, name=path.name, path=path))

    return sorted(migrations, key=lambda migration: migration.version)


def _ensure_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()


def _get_applied_migrations(connection: sqlite3.Connection) -> dict[int, str]:
    rows = connection.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _apply_migration(
    connection: sqlite3.Connection,
    migration: Migration,
) -> None:
    sql = migration.path.read_text(encoding="utf-8")
    migration_name = migration.name.replace("'", "''")
    script = f"""
        BEGIN IMMEDIATE;
        {sql}
        INSERT INTO schema_migrations (version, name)
        VALUES ({migration.version}, '{migration_name}');
        COMMIT;
    """

    try:
        connection.executescript(script)
    except sqlite3.Error as error:
        if connection.in_transaction:
            connection.rollback()
        raise MigrationError(
            f"Could not apply migration {migration.name}: {error}"
        ) from error
