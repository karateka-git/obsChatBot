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

    def test_load_config_reads_optional_vk_settings(self) -> None:
        """VK token и group id остаются опциональными, но читаются из окружения."""
        with patch.dict(
            os.environ,
            _env(VK_BOT_TOKEN="vk-token", VK_GROUP_ID="123"),
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.vk_bot_token, "vk-token")
        self.assertEqual(config.vk_group_id, 123)
        self.assertEqual(config.safe_summary()["vk_bot_token"], "set")

    def test_load_config_defaults_debug_to_false(self) -> None:
        """Без APP_DEBUG приложение работает в обычном logging-режиме."""
        with patch.dict(os.environ, _env(), clear=True):
            config = load_config()

        self.assertFalse(config.app_debug)

    def test_load_config_reads_optional_github_app_group(self) -> None:
        """GitHub App включается только полным набором безопасных настроек."""
        with patch.dict(
            os.environ,
            _env(
                GITHUB_APP_ID="12345",
                GITHUB_CLIENT_ID="Iv1.client",
                GITHUB_APP_SLUG="obs-chat-bot",
                GITHUB_PRIVATE_KEY_PATH="data/github-app.pem",
            ),
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.github_app.app_id, 12345)
        self.assertEqual(config.github_app.client_id, "Iv1.client")
        self.assertEqual(
            config.github_app.installation_url,
            "https://github.com/apps/obs-chat-bot/installations/new",
        )
        self.assertNotIn("Iv1.client", config.safe_summary().values())

    def test_load_config_leaves_github_disabled_when_group_is_empty(self) -> None:
        """Пустая GitHub-группа не мешает запускать ещё не настроенный connector."""
        with patch.dict(os.environ, _env(), clear=True):
            config = load_config()

        self.assertIsNone(config.github_app)

    def test_load_config_rejects_partial_github_app_group(self) -> None:
        """Частичная GitHub-конфигурация не допускает неоднозначный runtime."""
        with patch.dict(
            os.environ,
            _env(GITHUB_APP_ID="12345", GITHUB_CLIENT_ID="Iv1.client"),
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                load_config()

    def test_load_config_rejects_invalid_debug_flag(self) -> None:
        """Некорректное boolean-значение APP_DEBUG считается ошибкой конфига."""
        with patch.dict(os.environ, _env(APP_DEBUG="maybe"), clear=True):
            with self.assertRaises(ConfigError):
                load_config()

    def test_load_config_rejects_invalid_vk_group_id(self) -> None:
        """Некорректный VK_GROUP_ID считается ошибкой конфига."""
        with patch.dict(os.environ, _env(VK_GROUP_ID="bad"), clear=True):
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
        "GITHUB_APP_ID": "",
        "GITHUB_CLIENT_ID": "",
        "GITHUB_APP_SLUG": "",
        "GITHUB_PRIVATE_KEY_PATH": "",
    }
    values.update(overrides)
    return values


if __name__ == "__main__":
    unittest.main()
