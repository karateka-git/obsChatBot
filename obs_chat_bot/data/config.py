from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
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
class ChunkingConfig:
    """Содержит технические размеры chunks для composition root."""

    minimum_size_chars: int = 300
    target_size_chars: int = 3000
    maximum_size_chars: int = 6000

    def __post_init__(self) -> None:
        if self.minimum_size_chars <= 0:
            raise ValueError("minimum_size_chars must be positive")
        if self.target_size_chars < self.minimum_size_chars:
            raise ValueError(
                "target_size_chars must not be less than minimum_size_chars"
            )
        if self.maximum_size_chars < self.target_size_chars:
            raise ValueError(
                "maximum_size_chars must not be less than target_size_chars"
            )


@dataclass(frozen=True)
class GitHubAppConfig:
    """Содержит безопасные настройки зарегистрированного GitHub App."""

    app_id: int
    client_id: str
    app_slug: str
    private_key_path: Path

    def __post_init__(self) -> None:
        if self.app_id <= 0:
            raise ValueError("app_id must be positive")
        if not self.client_id.strip():
            raise ValueError("client_id must not be empty")
        if any(character.isspace() for character in self.client_id):
            raise ValueError("client_id must not contain whitespace")
        if re.fullmatch(r"[a-z0-9-]+", self.app_slug) is None:
            raise ValueError("app_slug has unexpected format")
        if not str(self.private_key_path).strip():
            raise ValueError("private_key_path must not be empty")

    @property
    def installation_url(self) -> str:
        """Возвращает прямую ссылку установки GitHub App."""
        return f"https://github.com/apps/{self.app_slug}/installations/new"


@dataclass(frozen=True)
class EmbeddingConfig:
    """Содержит отдельные настройки semantic embedding provider."""

    base_url: str
    api_key: str
    model: str

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url must not be empty")
        if not self.api_key.strip():
            raise ValueError("api_key must not be empty")
        if not self.model.strip():
            raise ValueError("model must not be empty")


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    database_path: Path
    telegram_bot_token: str
    openai_base_url: str
    openai_api_key: str
    openai_model: str
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    app_debug: bool = False
    vk_bot_token: str = ""
    vk_group_id: int | None = None
    github_app: GitHubAppConfig | None = None
    embedding: EmbeddingConfig | None = None

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
            "chunk_minimum_size_chars": str(self.chunking.minimum_size_chars),
            "chunk_target_size_chars": str(self.chunking.target_size_chars),
            "chunk_maximum_size_chars": str(self.chunking.maximum_size_chars),
            "app_debug": str(self.app_debug).lower(),
            "vk_bot_token": _presence(self.vk_bot_token),
            "vk_group_id": (
                str(self.vk_group_id)
                if self.vk_group_id is not None
                else "missing"
            ),
            "github_app": "configured" if self.github_app is not None else "missing",
            "github_private_key": (
                "set" if self.github_app is not None else "missing"
            ),
            "embedding_base_url": (
                self.embedding.base_url if self.embedding is not None else "missing"
            ),
            "embedding_api_key": (
                "set" if self.embedding is not None else "missing"
            ),
            "embedding_model": (
                self.embedding.model if self.embedding is not None else "missing"
            ),
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
        chunking=_load_chunking_config(),
        app_debug=_get_bool("APP_DEBUG", default=False),
        vk_bot_token=os.getenv("VK_BOT_TOKEN", ""),
        vk_group_id=_get_optional_int("VK_GROUP_ID"),
        github_app=_load_github_app_config(),
        embedding=_load_embedding_config(),
    )


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _presence(value: str) -> str:
    return "set" if value else "missing"


def _get_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"Environment variable {name} must be boolean")


def _get_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError as error:
        raise ConfigError(f"Environment variable {name} must be integer") from error
    if parsed <= 0:
        raise ConfigError(f"Environment variable {name} must be positive")
    return parsed


def _get_positive_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ConfigError(f"Environment variable {name} must be integer") from error
    if parsed <= 0:
        raise ConfigError(f"Environment variable {name} must be positive")
    return parsed


def _load_chunking_config() -> ChunkingConfig:
    try:
        return ChunkingConfig(
            minimum_size_chars=_get_positive_int(
                "CHUNK_MINIMUM_SIZE_CHARS",
                default=300,
            ),
            target_size_chars=_get_positive_int(
                "CHUNK_TARGET_SIZE_CHARS",
                default=3000,
            ),
            maximum_size_chars=_get_positive_int(
                "CHUNK_MAXIMUM_SIZE_CHARS",
                default=6000,
            ),
        )
    except ValueError as error:
        raise ConfigError(f"Invalid chunking configuration: {error}") from error


def _load_github_app_config() -> GitHubAppConfig | None:
    names = (
        "GITHUB_APP_ID",
        "GITHUB_CLIENT_ID",
        "GITHUB_APP_SLUG",
        "GITHUB_PRIVATE_KEY_PATH",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    configured = [name for name, value in values.items() if value]
    if not configured:
        return None

    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(
            "GitHub App configuration is incomplete; missing: " + ", ".join(missing)
        )
    try:
        app_id = int(values["GITHUB_APP_ID"])
    except ValueError as error:
        raise ConfigError(
            "Environment variable GITHUB_APP_ID must be integer"
        ) from error
    if app_id <= 0:
        raise ConfigError("Environment variable GITHUB_APP_ID must be positive")

    try:
        return GitHubAppConfig(
            app_id=app_id,
            client_id=values["GITHUB_CLIENT_ID"],
            app_slug=values["GITHUB_APP_SLUG"],
            private_key_path=Path(values["GITHUB_PRIVATE_KEY_PATH"]),
        )
    except ValueError as error:
        raise ConfigError(f"Invalid GitHub App configuration: {error}") from error


def _load_embedding_config() -> EmbeddingConfig | None:
    """Загружает независимую all-or-none группу настроек embeddings."""
    names = (
        "EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    configured = [name for name, value in values.items() if value]
    if not configured:
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(
            "Embedding configuration is incomplete; missing: " + ", ".join(missing)
        )
    try:
        return EmbeddingConfig(
            base_url=values["EMBEDDING_BASE_URL"].rstrip("/"),
            api_key=values["EMBEDDING_API_KEY"],
            model=values["EMBEDDING_MODEL"],
        )
    except ValueError as error:
        raise ConfigError(f"Invalid embedding configuration: {error}") from error
