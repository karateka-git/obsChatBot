"""Тесты загрузки конфигурации приложения."""

import os
import unittest
from unittest.mock import patch

from obs_chat_bot.data.config import ConfigError, load_config


class ConfigTest(unittest.TestCase):
    """Проверяет чтение `.env`-настроек."""

    def test_load_config_reads_optional_debug_flag(self) -> None:
        """APP_DEBUG включает debug-режим, но остаётся опциональным."""
        with patch.dict(os.environ, _env(APP_DEBUG="true"), clear=True):
            config = load_config()

        self.assertTrue(config.app_debug)
        self.assertEqual(config.safe_summary()["app_debug"], "true")

    def test_load_config_defaults_debug_to_false(self) -> None:
        """Без APP_DEBUG приложение работает в обычном logging-режиме."""
        with patch.dict(os.environ, _env(), clear=True):
            config = load_config()

        self.assertFalse(config.app_debug)

    def test_load_config_rejects_invalid_debug_flag(self) -> None:
        """Некорректное boolean-значение APP_DEBUG считается ошибкой конфига."""
        with patch.dict(os.environ, _env(APP_DEBUG="maybe"), clear=True):
            with self.assertRaises(ConfigError):
                load_config()


def _env(**overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "test",
        "DATABASE_PATH": "data/test.db",
        "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyz",
        "OPENAI_BASE_URL": "https://llm.example/v1",
        "OPENAI_API_KEY": "token",
        "OPENAI_MODEL": "fake-model",
    }
    values.update(overrides)
    return values


if __name__ == "__main__":
    unittest.main()
