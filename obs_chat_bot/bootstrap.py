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
from obs_chat_bot.application.vaults.ports import GitHubConnectionStarter
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
from obs_chat_bot.data.sqlite.processing_error_repository import (
    SQLiteProcessingErrorRecorder,
)
from obs_chat_bot.data.sqlite.user_identity_repository import (
    SQLiteAppUserRepository,
    SQLiteExternalIdentityRepository,
    SQLiteIdentityRebindConfirmationRepository,
    SQLiteIdentityLinkTokenRepository,
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
) -> ProcessIncomingMessageUseCase:
    """Собирает общий сценарий обработки входящего сообщения из любого канала."""
    return ProcessIncomingMessageUseCase(
        article_url_use_case=article_url_use_case,
        article_analysis_use_case=article_analysis_use_case,
        incoming_message_repository=incoming_message_repository,
        user_identity_service=user_identity_service,
        github_connection_starter=github_connection_starter,
    )


def create_github_connection_coordinator(
    *,
    database_path: Path,
    config: GitHubAppConfig,
) -> GitHubConnectionCoordinator:
    """Собирает процессный coordinator GitHub Device Flow.

    Args:
        database_path: Путь к общей SQLite-базе adapters.
        config: Полная конфигурация зарегистрированного GitHub App.

    Returns:
        Coordinator, хранящий временные Device Flow sessions только в памяти.
    """
    signer = PyJwtGitHubAppSigner(
        client_id=config.client_id,
        private_key_path=config.private_key_path,
    )
    gateway = UrllibGitHubAppClient(
        client_id=config.client_id,
        app_jwt_factory=signer.create,
    )
    return GitHubConnectionCoordinator(
        gateway=gateway,
        account_writer=SQLiteGitHubAccountAccessWriter(database_path),
        state_store=SQLiteGitHubConnectionStateStore(database_path),
        installation_url=config.installation_url,
    )
