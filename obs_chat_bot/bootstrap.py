from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from obs_chat_bot.application.articles.analysis import AnalyzeArticleUseCase
from obs_chat_bot.application.articles.ports import IncomingMessageRepository
from obs_chat_bot.application.articles.processing import ProcessArticleUrlUseCase
from obs_chat_bot.application.users.identity import UserIdentityService
from obs_chat_bot.data.extraction.trafilatura_article_extractor import (
    TrafilaturaArticleTextExtractor,
)
from obs_chat_bot.data.http.article_html_fetcher import UrllibArticleHtmlFetcher
from obs_chat_bot.data.llm.openai_article_analyzer import OpenAIArticleAnalyzer
from obs_chat_bot.data.sqlite.analysis_result_repository import (
    SQLiteArticleAnalysisResultRepository,
)
from obs_chat_bot.data.sqlite.article_repository import SQLiteArticleRepository
from obs_chat_bot.data.sqlite.incoming_message_repository import (
    SQLiteIncomingMessageRepository,
)
from obs_chat_bot.data.sqlite.processing_error_repository import (
    SQLiteProcessingErrorRecorder,
)
from obs_chat_bot.data.sqlite.user_identity_repository import (
    SQLiteAppUserRepository,
    SQLiteExternalIdentityRepository,
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


@dataclass(frozen=True, slots=True)
class TelegramBotDependencies:
    """Группирует concrete dependencies Telegram adapter.

    Composition root собирает зависимости в одном месте, чтобы CLI и будущие
    entrypoints не знали о конкретных SQLite, HTTP, extraction и LLM adapters.
    """

    article_url_use_case: ProcessArticleUrlUseCase
    article_analysis_use_case: AnalyzeArticleUseCase
    incoming_message_repository: IncomingMessageRepository
    user_identity_service: UserIdentityService


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
    )


def create_telegram_bot_dependencies(
    connection: sqlite3.Connection,
    *,
    openai_base_url: str,
    openai_api_key: str,
    openai_model: str,
) -> TelegramBotDependencies:
    """Собирает все concrete dependencies Telegram adapter.

    Args:
        connection: Открытое соединение SQLite.
        openai_base_url: Базовый URL OpenAI-compatible API.
        openai_api_key: API key провайдера LLM.
        openai_model: Имя модели для анализа статей.

    Returns:
        Группа зависимостей для запуска Telegram adapter.
    """
    return TelegramBotDependencies(
        article_url_use_case=create_process_article_url_use_case(connection),
        article_analysis_use_case=create_analyze_article_use_case(
            connection,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
        ),
        incoming_message_repository=create_incoming_message_repository(connection),
        user_identity_service=create_user_identity_service(connection),
    )
