from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from obs_chat_bot.application.articles.analysis import (
    AnalyzeArticleCommand,
    AnalyzeArticleError,
    AnalyzeArticleResult,
    AnalyzeArticleUseCase,
)
from obs_chat_bot.application.articles.incoming_messages import (
    IncomingMessage,
    SavedIncomingMessage,
)
from obs_chat_bot.application.articles.ports import IncomingMessageRepository
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlError,
    ProcessArticleUrlResult,
    ProcessArticleUrlUseCase,
)
from obs_chat_bot.application.articles.url_extraction import extract_first_supported_url
from obs_chat_bot.application.users.identity import (
    CreatedLinkCode,
    IdentityAlreadyBoundError,
    InvalidLinkCodeError,
    UserIdentityService,
)
from obs_chat_bot.domain.users.entities import AppUser, IncomingIdentity


class IncomingMessageResultType(StrEnum):
    """Тип результата обработки входящего сообщения."""

    UNKNOWN_IDENTITY = "unknown_identity"
    REGISTERED = "registered"
    LINK_CODE_CREATED = "link_code_created"
    LINK_COMMAND_INVALID = "link_command_invalid"
    LINKED = "linked"
    LINK_ALREADY_BOUND = "link_already_bound"
    LINK_CODE_INVALID = "link_code_invalid"
    ARTICLE_URL_MISSING = "article_url_missing"
    ARTICLE_PROCESSED = "article_processed"
    ARTICLE_ANALYZED = "article_analyzed"
    ARTICLE_PROCESSING_FAILED = "article_processing_failed"
    ARTICLE_ANALYSIS_FAILED = "article_analysis_failed"


@dataclass(frozen=True, slots=True)
class ProcessIncomingMessageResult:
    """Структурированный результат обработки входящего сообщения."""

    type: IncomingMessageResultType
    app_user: AppUser | None = None
    saved_message: SavedIncomingMessage | None = None
    link_code: CreatedLinkCode | None = None
    article_result: ProcessArticleUrlResult | None = None
    analysis_result: AnalyzeArticleResult | None = None
    error: Exception | None = None


class ProcessIncomingMessageUseCase:
    """Обрабатывает входящее сообщение без привязки к конкретному каналу."""

    def __init__(
        self,
        *,
        article_url_use_case: ProcessArticleUrlUseCase,
        article_analysis_use_case: AnalyzeArticleUseCase | None = None,
        incoming_message_repository: IncomingMessageRepository | None = None,
        user_identity_service: UserIdentityService | None = None,
    ) -> None:
        self._article_url_use_case = article_url_use_case
        self._article_analysis_use_case = article_analysis_use_case
        self._incoming_message_repository = incoming_message_repository
        self._user_identity_service = user_identity_service

    def execute(self, incoming_message: IncomingMessage) -> ProcessIncomingMessageResult:
        """Выполняет общий flow регистрации, сохранения статьи и анализа."""
        app_user_result = self._resolve_app_user(incoming_message)
        if isinstance(app_user_result, ProcessIncomingMessageResult):
            return app_user_result

        incoming_message = _with_app_user(incoming_message, app_user_result)
        url = extract_first_supported_url(incoming_message.text)
        if url is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_URL_MISSING,
                app_user=app_user_result,
            )

        saved_message = self._save_incoming_message(incoming_message)
        incoming_message_id = saved_message.id if saved_message is not None else None

        try:
            article_result = self._article_url_use_case.execute(
                ProcessArticleUrlCommand(
                    source_url=url,
                    app_user_id=incoming_message.app_user_id,
                    incoming_message_id=incoming_message_id,
                )
            )
        except ProcessArticleUrlError as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_PROCESSING_FAILED,
                app_user=app_user_result,
                saved_message=saved_message,
                error=error,
            )

        self._link_message_to_article(saved_message, article_result)

        if self._article_analysis_use_case is None or article_result.article.id is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_PROCESSED,
                app_user=app_user_result,
                saved_message=saved_message,
                article_result=article_result,
            )

        try:
            analysis_result = self._article_analysis_use_case.execute(
                AnalyzeArticleCommand(
                    article_id=article_result.article.id,
                    app_user_id=incoming_message.app_user_id,
                    incoming_message_id=incoming_message_id,
                )
            )
        except AnalyzeArticleError as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_ANALYSIS_FAILED,
                app_user=app_user_result,
                saved_message=saved_message,
                article_result=article_result,
                error=error,
            )

        return ProcessIncomingMessageResult(
            type=IncomingMessageResultType.ARTICLE_ANALYZED,
            app_user=app_user_result,
            saved_message=saved_message,
            article_result=article_result,
            analysis_result=analysis_result,
        )

    def _resolve_app_user(
        self,
        incoming_message: IncomingMessage,
    ) -> AppUser | ProcessIncomingMessageResult:
        """Определяет пользователя приложения или возвращает результат onboarding."""
        if self._user_identity_service is None:
            return AppUser(id=incoming_message.app_user_id)

        identity = _incoming_identity_from_message(incoming_message)
        text = incoming_message.text.strip()

        if text == "/register":
            app_user = self._user_identity_service.register(identity)
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.REGISTERED,
                app_user=app_user,
            )

        if text == "/link_code":
            app_user = self._user_identity_service.resolve(identity)
            if app_user is None:
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.UNKNOWN_IDENTITY
                )
            link_code = self._user_identity_service.create_link_code(app_user.id)
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_CODE_CREATED,
                app_user=app_user,
                link_code=link_code,
            )

        if text.startswith("/link"):
            parts = text.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].strip():
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.LINK_COMMAND_INVALID
                )
            try:
                app_user = self._user_identity_service.link(
                    code=parts[1],
                    identity=identity,
                )
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.LINKED,
                    app_user=app_user,
                )
            except IdentityAlreadyBoundError as error:
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.LINK_ALREADY_BOUND,
                    error=error,
                )
            except InvalidLinkCodeError as error:
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.LINK_CODE_INVALID,
                    error=error,
                )

        app_user = self._user_identity_service.resolve(identity)
        if app_user is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.UNKNOWN_IDENTITY
            )
        return app_user

    def _save_incoming_message(
        self,
        incoming_message: IncomingMessage,
    ) -> SavedIncomingMessage | None:
        """Сохраняет сообщение, если repository передан в use case."""
        if self._incoming_message_repository is None:
            return None
        return self._incoming_message_repository.save(incoming_message)

    def _link_message_to_article(
        self,
        saved_message: SavedIncomingMessage | None,
        article_result: ProcessArticleUrlResult,
    ) -> None:
        """Связывает сохраненное сообщение со статьей после успешной обработки."""
        if (
            self._incoming_message_repository is None
            or saved_message is None
            or article_result.article.id is None
        ):
            return
        self._incoming_message_repository.link_to_article(
            incoming_message_id=saved_message.id,
            article_id=article_result.article.id,
        )


def _incoming_identity_from_message(incoming_message: IncomingMessage) -> IncomingIdentity:
    """Преобразует входящее сообщение в identity внешнего канала."""
    external_user_id = incoming_message.external_user_id or incoming_message.chat_id
    return IncomingIdentity(
        channel=incoming_message.channel,
        external_user_id=external_user_id,
        external_chat_id=incoming_message.chat_id,
        username=incoming_message.username,
        display_name=incoming_message.display_name,
    )


def _with_app_user(incoming_message: IncomingMessage, app_user: AppUser) -> IncomingMessage:
    """Возвращает копию входящего сообщения с ID пользователя приложения."""
    return IncomingMessage(
        channel=incoming_message.channel,
        chat_id=incoming_message.chat_id,
        message_id=incoming_message.message_id,
        text=incoming_message.text,
        app_user_id=app_user.id,
        external_user_id=incoming_message.external_user_id,
        username=incoming_message.username,
        display_name=incoming_message.display_name,
    )
