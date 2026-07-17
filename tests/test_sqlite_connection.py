"""Тесты настройки SQLite-соединения."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from obs_chat_bot.data.sqlite.connection import connect_database


class SQLiteConnectionTest(unittest.TestCase):
    """Проверяет runtime-настройки SQLite connection."""

    def test_allow_cross_thread_enables_worker_thread_usage(self) -> None:
        """Telegram worker thread может использовать явно разрешённое connection."""
        with TemporaryDirectory(prefix="obs-chat-bot-sqlite-connection-") as directory:
            with connect_database(
                Path(directory) / "test.db",
                allow_cross_thread=True,
            ) as connection:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    result = executor.submit(
                        lambda: connection.execute("SELECT 1").fetchone()[0]
                    ).result()

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
