from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


REQUIRED_ENV_VARS = (
    "APP_ENV",
    "DATABASE_PATH",
    "TELEGRAM_BOT_TOKEN",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
)


class ConfigError(ValueError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    database_path: Path
    telegram_bot_token: str
    openai_base_url: str
    openai_api_key: str
    openai_model: str

    @property
    def data_dir(self) -> Path:
        return self.database_path.parent

    def safe_summary(self) -> dict[str, str]:
        return {
            "app_env": self.app_env,
            "database_path": str(self.database_path),
            "telegram_bot_token": _presence(self.telegram_bot_token),
            "openai_base_url": self.openai_base_url,
            "openai_api_key": _presence(self.openai_api_key),
            "openai_model": self.openai_model,
        }


def load_config() -> AppConfig:
    if load_dotenv is not None:
        load_dotenv()

    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(f"Missing required environment variables: {joined}")

    return AppConfig(
        app_env=_get_required("APP_ENV"),
        database_path=Path(_get_required("DATABASE_PATH")),
        telegram_bot_token=_get_required("TELEGRAM_BOT_TOKEN"),
        openai_base_url=_get_required("OPENAI_BASE_URL").rstrip("/"),
        openai_api_key=_get_required("OPENAI_API_KEY"),
        openai_model=_get_required("OPENAI_MODEL"),
    )


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _presence(value: str) -> str:
    return "set" if value else "missing"
