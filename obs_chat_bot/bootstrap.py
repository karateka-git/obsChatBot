from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from obs_chat_bot.application.articles.analysis import AnalyzeArticleUseCase
from obs_chat_bot.application.articles.ports import IncomingMessageRepository
from obs_chat_bot.application.articles.processing import ProcessArticleUrlUseCase
from obs_chat_bot.application.incoming.processing import ProcessIncomingMessageUseCase
from obs_chat_bot.application.users.identity import UserIdentityService
from obs_chat_bot.application.vaults.github_connection import (
    GitHubConnectionCoordinator,
)
from obs_chat_bot.application.vaults.ports import (
    GitHubConnectionStarter,
    GitHubRepositoryGateway,
)
from obs_chat_bot.application.vaults.vault_selection import (
    GitHubVaultSelectionService,
    VaultSelectionManager,
)
from obs_chat_bot.data.config import GitHubAppConfig
from obs_chat_bot.data.extraction.trafilatura_article_extractor import (
    TrafilaturaArticleTextExtractor,
)
from obs_chat_bot.data.http.article_html_fetcher import UrllibArticleHtmlFetcher
from obs_chat_bot.data.llm.openai_article_analyzer import OpenAIArticleAnalyzer
from obs_chat_bot.data.github.github_app_client import UrllibGitHubAppClient
from obs_chat_bot.data.github.jwt_signer import PyJwtGitHubAppSigner
from obs_chat_bot.data.sqlite.analysis_result_repository import (
    SQLiteArticleAnalysisResultRepository,
)
from obs_chat_bot.data.sqlite.article_repository import SQLiteArticleRepository
from obs_chat_bot.data.sqlite.incoming_message_repository import (
    SQLiteIncomingMessageRepository,
)
from obs_chat_bot.data.sqlite.github_installation_writer import (
    SQLiteGitHubAccountAccessWriter,
)
from obs_chat_bot.data.sqlite.github_connection_state_store import (
    SQLiteGitHubConnectionStateStore,
)
from obs_chat_bot.data.sqlite.github_installation_repository import (
    SQLiteGitHubInstallationRepository,
)
from obs_chat_bot.data.sqlite.obsidian_vault_repository import (
    SQLiteObsidianVaultRepository,
)
from obs_chat_bot.data.sqlite.processing_error_repository import (
    SQLiteProcessingErrorRecorder,
)
from obs_chat_bot.data.sqlite.user_identity_repository import (
    SQLiteAppUserRepository,
    SQLiteExternalIdentityRepository,
    SQLiteIdentityRebindConfirmationRepository,
    SQLiteIdentityLinkTokenRepository,
)
from obs_chat_bot.data.sqlite.vault_confirmation_repository import (
    SQLiteVaultActionConfirmationRepository,
)


ProcessArticleUrlUseCaseFactory = Callable[
    [sqlite3.Connection],
    ProcessArticleUrlUseCase,
]
AnalyzeArticleUseCaseFactory = Callable[
    [sqlite3.Connection],
    AnalyzeArticleUseCase,
]


def create_process_article_url_use_case(
    connection: sqlite3.Connection,
) -> ProcessArticleUrlUseCase:
    """Собирает concrete dependencies для обработки URL статьи.

    Args:
        connection: Открытое соединение SQLite.

    Returns:
        Use case с SQLite, HTTP и trafilatura-реализациями ports.
    """
    return ProcessArticleUrlUseCase(
        article_repository=SQLiteArticleRepository(connection),
        html_fetcher=UrllibArticleHtmlFetcher(),
        text_extractor=TrafilaturaArticleTextExtractor(),
        error_recorder=SQLiteProcessingErrorRecorder(connection),
    )


def create_analyze_article_use_case(
    connection: sqlite3.Connection,
    *,
    openai_base_url: str,
    openai_api_key: str,
    openai_model: str,
) -> AnalyzeArticleUseCase:
    """Собирает concrete dependencies для LLM-анализа статьи.

    Args:
        connection: Открытое соединение SQLite.
        openai_base_url: Базовый URL OpenAI-compatible API.
        openai_api_key: API key провайдера LLM.
        openai_model: Имя модели для анализа статей.

    Returns:
        Use case с SQLite-хранилищем и OpenAI-compatible analyzer.
    """
    return AnalyzeArticleUseCase(
        article_repository=SQLiteArticleRepository(connection),
        analyzer=OpenAIArticleAnalyzer(
            base_url=openai_base_url,
            api_key=openai_api_key,
            model=openai_model,
        ),
        analysis_result_repository=SQLiteArticleAnalysisResultRepository(connection),
        error_recorder=SQLiteProcessingErrorRecorder(connection),
    )


def create_incoming_message_repository(
    connection: sqlite3.Connection,
) -> IncomingMessageRepository:
    """Создаёт repository входящих сообщений для adapters каналов."""
    return SQLiteIncomingMessageRepository(connection)


def create_user_identity_service(connection: sqlite3.Connection) -> UserIdentityService:
    """Собирает сервис регистрации пользователей и привязки внешних каналов."""
    return UserIdentityService(
        app_user_repository=SQLiteAppUserRepository(connection),
        external_identity_repository=SQLiteExternalIdentityRepository(connection),
        link_token_repository=SQLiteIdentityLinkTokenRepository(connection),
        rebind_confirmation_repository=SQLiteIdentityRebindConfirmationRepository(
            connection
        ),
    )


def create_process_incoming_message_use_case(
    *,
    article_url_use_case: ProcessArticleUrlUseCase,
    article_analysis_use_case: AnalyzeArticleUseCase | None,
    incoming_message_repository: IncomingMessageRepository | None,
    user_identity_service: UserIdentityService | None,
    github_connection_starter: GitHubConnectionStarter | None = None,
    vault_selection_manager: VaultSelectionManager | None = None,
) -> ProcessIncomingMessageUseCase:
    """Собирает общий сценарий обработки входящего сообщения из любого канала.

    Args:
        article_url_use_case: Сценарий загрузки и сохранения статьи.
        article_analysis_use_case: Сценарий LLM-анализа или `None`.
        incoming_message_repository: Хранилище входящих сообщений или `None`.
        user_identity_service: Сервис пользователей и identities или `None`.
        github_connection_starter: Coordinator GitHub Device Flow или `None`.
        vault_selection_manager: Сценарий выбора GitHub vault или `None`.

    Returns:
        Настроенный channel-agnostic incoming use case.
    """
    return ProcessIncomingMessageUseCase(
        article_url_use_case=article_url_use_case,
        article_analysis_use_case=article_analysis_use_case,
        incoming_message_repository=incoming_message_repository,
        user_identity_service=user_identity_service,
        github_connection_starter=github_connection_starter,
        vault_selection_manager=vault_selection_manager,
    )


def create_github_app_client(config: GitHubAppConfig) -> UrllibGitHubAppClient:
    """Создаёт общий HTTP adapter зарегистрированного GitHub App.

    Args:
        config: Полная конфигурация GitHub App.

    Returns:
        Client для Device Flow, installation tokens и чтения repositories.
    """
    signer = PyJwtGitHubAppSigner(
        client_id=config.client_id,
        private_key_path=config.private_key_path,
    )
    return UrllibGitHubAppClient(
        client_id=config.client_id,
        app_jwt_factory=signer.create,
    )


def create_vault_selection_manager(
    *,
    connection: sqlite3.Connection,
    github_gateway: GitHubRepositoryGateway,
) -> VaultSelectionManager:
    """Собирает application-сценарий выбора vault для одного сообщения.

    Args:
        connection: Соединение SQLite текущего worker.
        github_gateway: Процессный GitHub App HTTP adapter.

    Returns:
        Сервис с общими SQLite repositories пользователя.
    """
    return GitHubVaultSelectionService(
        installation_repository=SQLiteGitHubInstallationRepository(connection),
        vault_repository=SQLiteObsidianVaultRepository(connection),
        confirmation_repository=SQLiteVaultActionConfirmationRepository(connection),
        github_gateway=github_gateway,
    )


def create_github_connection_coordinator(
    *,
    database_path: Path,
    config: GitHubAppConfig,
    gateway: UrllibGitHubAppClient | None = None,
) -> GitHubConnectionCoordinator:
    """Собирает процессный coordinator GitHub Device Flow.

    Args:
        database_path: Путь к общей SQLite-базе adapters.
        config: Полная конфигурация зарегистрированного GitHub App.
        gateway: Общий процессный GitHub client или `None` для создания нового.

    Returns:
        Coordinator, хранящий временные Device Flow sessions только в памяти.
    """
    runtime_gateway = gateway or create_github_app_client(config)
    return GitHubConnectionCoordinator(
        gateway=runtime_gateway,
        account_writer=SQLiteGitHubAccountAccessWriter(database_path),
        state_store=SQLiteGitHubConnectionStateStore(database_path),
        installation_url=config.installation_url,
    )
