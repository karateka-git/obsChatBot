from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


BUSY_TIMEOUT_MS = 5_000


@contextmanager
def connect_database(
    database_path: Path,
    *,
    allow_cross_thread: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Открывает SQLite-соединение и применяет runtime PRAGMA.

    Args:
        database_path: Путь к файлу SQLite.
        allow_cross_thread: Разрешает использовать connection из worker thread.
            Это нужно Telegram adapter, который выносит blocking pipeline из
            event loop и дополнительно сериализует доступ lock'ом.

    Yields:
        Настроенное SQLite-соединение.
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        database_path,
        timeout=BUSY_TIMEOUT_MS / 1_000,
        check_same_thread=not allow_cross_thread,
    )

    try:
        connection.row_factory = sqlite3.Row
        _configure_connection(connection)
        yield connection
    finally:
        connection.close()


def _configure_connection(connection: sqlite3.Connection) -> None:
    journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")

    if journal_mode is None or journal_mode[0].lower() != "wal":
        raise sqlite3.OperationalError("Could not enable WAL journal mode")

    busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()
    if busy_timeout is None or busy_timeout[0] != BUSY_TIMEOUT_MS:
        raise sqlite3.OperationalError("Could not configure busy timeout")

    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
    if foreign_keys is None or foreign_keys[0] != 1:
        raise sqlite3.OperationalError("Could not enable foreign keys")
