"""Общие helpers SQLite-тестов с явными пользовательскими fixtures."""

import sqlite3


def ensure_app_user(
    connection: sqlite3.Connection,
    *,
    app_user_id: int = 1,
) -> None:
    """Создаёт пользователя, от которого зависят тестовые данные."""
    connection.execute(
        "INSERT OR IGNORE INTO app_users (id, display_name) VALUES (?, ?)",
        (app_user_id, f"Test user {app_user_id}"),
    )
    connection.commit()
