from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import logging

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
from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionStartResult,
    GitHubConnectionStartStatus,
    GitHubGatewayError,
)
from obs_chat_bot.application.vaults.ports import (
    GitHubConnectionCompletionHandler,
    GitHubConnectionStarter,
)
from obs_chat_bot.application.vaults.vault_selection import (
    GitHubAccountNotConnectedError,
    GitHubRepositoryNotAccessibleError,
    GitHubVaultPathNotFoundError,
    VaultSelectionManager,
    VaultSelectionResult,
    VaultSelectionStatus,
)
from obs_chat_bot.domain.users.entities import AppUser, IncomingIdentity


LOGGER = logging.getLogger(__name__)


class IncomingMessageResultType(StrEnum):
    """Тип результата обработки входящего сообщения."""

    UNKNOWN_IDENTITY = "unknown_identity"
    START_UNREGISTERED = "start_unregistered"
    START_REGISTERED = "start_registered"
    REGISTERED = "registered"
    ALREADY_REGISTERED = "already_registered"
    LINK_CODE_CREATED = "link_code_created"
    LINK_COMMAND_INVALID = "link_command_invalid"
    LINKED = "linked"
    LINK_ALREADY_BOUND = "link_already_bound"
    LINK_CODE_INVALID = "link_code_invalid"
    LINK_REBIND_CONFIRMATION_REQUIRED = "link_rebind_confirmation_required"
    LINK_REBOUND = "link_rebound"
    LINK_REBIND_CANCELLED = "link_rebind_cancelled"
    LINK_REBIND_CONFIRMATION_MISSING = "link_rebind_confirmation_missing"
    LINK_REBIND_CONFIRMATION_PENDING = "link_rebind_confirmation_pending"
    STATUS = "status"
    REANALYZE_COMMAND_INVALID = "reanalyze_command_invalid"
    ARTICLE_REANALYZED = "article_reanalyzed"
    ARTICLE_REANALYSIS_FAILED = "article_reanalysis_failed"
    ARTICLE_URL_MISSING = "article_url_missing"
    ARTICLE_PROCESSED = "article_processed"
    ARTICLE_ANALYZED = "article_analyzed"
    ARTICLE_PROCESSING_FAILED = "article_processing_failed"
    ARTICLE_ANALYSIS_FAILED = "article_analysis_failed"
    GITHUB_CONNECT_STARTED = "github_connect_started"
    GITHUB_CONNECT_ALREADY_PENDING = "github_connect_already_pending"
    GITHUB_CONNECT_PREPARING = "github_connect_preparing"
    GITHUB_CONNECT_UNAVAILABLE = "github_connect_unavailable"
    GITHUB_CONNECT_FAILED = "github_connect_failed"
    GITHUB_RECONNECT_CONFIRMATION_REQUIRED = "github_reconnect_confirmation_required"
    GITHUB_RECONNECT_CANCELLED = "github_reconnect_cancelled"
    GITHUB_RECONNECT_CONFIRMATION_MISSING = "github_reconnect_confirmation_missing"
    GITHUB_CONNECT_IN_PROGRESS = "github_connect_in_progress"
    GITHUB_VAULT_COMMAND_INVALID = "github_vault_command_invalid"
    GITHUB_VAULT_SELECTED = "github_vault_selected"
    GITHUB_VAULT_ALREADY_SELECTED = "github_vault_already_selected"
    GITHUB_VAULT_REPLACEMENT_CONFIRMATION_REQUIRED = (
        "github_vault_replacement_confirmation_required"
    )
    GITHUB_VAULT_REPLACED = "github_vault_replaced"
    GITHUB_VAULT_REPLACEMENT_CANCELLED = "github_vault_replacement_cancelled"
    GITHUB_VAULT_CONFIRMATION_MISSING = "github_vault_confirmation_missing"
    GITHUB_VAULT_GITHUB_REQUIRED = "github_vault_github_required"
    GITHUB_VAULT_REPOSITORY_UNAVAILABLE = "github_vault_repository_unavailable"
    GITHUB_VAULT_PATH_NOT_FOUND = "github_vault_path_not_found"
    GITHUB_VAULT_FAILED = "github_vault_failed"


@dataclass(frozen=True, slots=True)
class ProcessIncomingMessageResult:
    """Структурированный результат обработки входящего сообщения."""

    type: IncomingMessageResultType
    app_user: AppUser | None = None
    saved_message: SavedIncomingMessage | None = None
    link_code: CreatedLinkCode | None = None
    article_result: ProcessArticleUrlResult | None = None
    analysis_result: AnalyzeArticleResult | None = None
    github_connection: GitHubConnectionStartResult | None = None
    vault_selection: VaultSelectionResult | None = None
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
        github_connection_starter: GitHubConnectionStarter | None = None,
        vault_selection_manager: VaultSelectionManager | None = None,
    ) -> None:
        self._article_url_use_case = article_url_use_case
        self._article_analysis_use_case = article_analysis_use_case
        self._incoming_message_repository = incoming_message_repository
        self._user_identity_service = user_identity_service
        self._github_connection_starter = github_connection_starter
        self._vault_selection_manager = vault_selection_manager

    def execute(
        self,
        incoming_message: IncomingMessage,
        github_completion_handler: GitHubConnectionCompletionHandler | None = None,
    ) -> ProcessIncomingMessageResult:
        """Выполняет общий flow регистрации, сохранения статьи и анализа.

        Args:
            incoming_message: Нормализованное сообщение внешнего канала.
            github_completion_handler: Callback итогового ответа Device Flow в
                исходный чат или `None`, если фоновый ответ не поддерживается.

        Returns:
            Структурированный результат синхронной части обработки.
        """
        LOGGER.debug(
            "Incoming message received: channel=%s chat_id=%s message_id=%s "
            "external_user_id=%s text_kind=%s",
            incoming_message.channel,
            incoming_message.chat_id,
            incoming_message.message_id,
            incoming_message.external_user_id,
            _text_kind(incoming_message.text),
        )
        app_user_result = self._resolve_app_user(
            incoming_message,
            github_completion_handler=github_completion_handler,
        )
        if isinstance(app_user_result, ProcessIncomingMessageResult):
            _log_result(app_user_result)
            return app_user_result

        incoming_message = _with_app_user(incoming_message, app_user_result)
        LOGGER.debug(
            "Incoming identity resolved: app_user_id=%s channel=%s chat_id=%s",
            app_user_result.id,
            incoming_message.channel,
            incoming_message.chat_id,
        )
        url = extract_first_supported_url(incoming_message.text)
        if url is None:
            result = ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_URL_MISSING,
                app_user=app_user_result,
            )
            _log_result(result)
            return result

        saved_message = self._save_incoming_message(incoming_message)
        incoming_message_id = saved_message.id if saved_message is not None else None
        if saved_message is not None:
            LOGGER.debug(
                "Incoming message saved: incoming_message_id=%s app_user_id=%s "
                "channel=%s chat_id=%s message_id=%s",
                saved_message.id,
                saved_message.app_user_id,
                saved_message.channel,
                saved_message.chat_id,
                saved_message.message_id,
            )

        try:
            article_result = self._article_url_use_case.execute(
                ProcessArticleUrlCommand(
                    source_url=url,
                    app_user_id=incoming_message.app_user_id,
                    incoming_message_id=incoming_message_id,
                )
            )
        except ProcessArticleUrlError as error:
            result = ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_PROCESSING_FAILED,
                app_user=app_user_result,
                saved_message=saved_message,
                error=error,
            )
            _log_result(result)
            return result

        self._link_message_to_article(saved_message, article_result)
        LOGGER.debug(
            "Article flow completed: article_id=%s app_user_id=%s created=%s "
            "extracted=%s status=%s",
            article_result.article.id,
            article_result.article.app_user_id,
            article_result.created,
            article_result.extracted,
            article_result.article.status.value,
        )

        if self._article_analysis_use_case is None or article_result.article.id is None:
            result = ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_PROCESSED,
                app_user=app_user_result,
                saved_message=saved_message,
                article_result=article_result,
            )
            _log_result(result)
            return result

        try:
            analysis_result = self._article_analysis_use_case.execute(
                AnalyzeArticleCommand(
                    article_id=article_result.article.id,
                    app_user_id=incoming_message.app_user_id,
                    incoming_message_id=incoming_message_id,
                )
            )
        except AnalyzeArticleError as error:
            result = ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_ANALYSIS_FAILED,
                app_user=app_user_result,
                saved_message=saved_message,
                article_result=article_result,
                error=error,
            )
            _log_result(result)
            return result

        LOGGER.debug(
            "Article analysis completed: article_id=%s analysis_id=%s created=%s "
            "model=%s",
            analysis_result.article.id,
            analysis_result.analysis.id,
            analysis_result.created,
            analysis_result.analysis.llm_model,
        )
        result = ProcessIncomingMessageResult(
            type=IncomingMessageResultType.ARTICLE_ANALYZED,
            app_user=app_user_result,
            saved_message=saved_message,
            article_result=article_result,
            analysis_result=analysis_result,
        )
        _log_result(result)
        return result

    def _resolve_app_user(
        self,
        incoming_message: IncomingMessage,
        *,
        github_completion_handler: GitHubConnectionCompletionHandler | None,
    ) -> AppUser | ProcessIncomingMessageResult:
        """Определяет пользователя приложения или возвращает результат onboarding."""
        if self._user_identity_service is None:
            return AppUser(id=incoming_message.app_user_id)

        identity = _incoming_identity_from_message(incoming_message)
        text = incoming_message.text.strip()
        normalized_text = text.lower()

        if normalized_text in {"да", "yes", "y"}:
            if self._user_identity_service.has_pending_rebind(identity):
                try:
                    app_user = self._user_identity_service.confirm_rebind(identity)
                    return ProcessIncomingMessageResult(
                        type=IncomingMessageResultType.LINK_REBOUND,
                        app_user=app_user,
                    )
                except InvalidLinkCodeError as error:
                    return ProcessIncomingMessageResult(
                        type=IncomingMessageResultType.LINK_REBIND_CONFIRMATION_MISSING,
                        error=error,
                    )
            app_user = self._user_identity_service.resolve(identity)
            if (
                app_user is not None
                and self._github_connection_starter is not None
                and self._github_connection_starter.has_reconnect_confirmation(
                    app_user.id
                )
            ):
                return self._confirm_github_reconnect(
                    app_user,
                    github_completion_handler=github_completion_handler,
                )
            if (
                app_user is not None
                and self._vault_selection_manager is not None
                and self._vault_selection_manager.has_replacement_confirmation(
                    app_user.id
                )
            ):
                return self._confirm_vault_replacement(app_user)
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_REBIND_CONFIRMATION_MISSING
            )

        if normalized_text in {"нет", "no", "n"}:
            if self._user_identity_service.has_pending_rebind(identity):
                self._user_identity_service.cancel_rebind(identity)
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.LINK_REBIND_CANCELLED
                )
            app_user = self._user_identity_service.resolve(identity)
            if (
                app_user is not None
                and self._github_connection_starter is not None
                and self._github_connection_starter.cancel_reconnect(app_user.id)
            ):
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.GITHUB_RECONNECT_CANCELLED,
                    app_user=app_user,
                )
            if app_user is not None and self._vault_selection_manager is not None:
                cancelled = self._vault_selection_manager.cancel_replacement(
                    app_user.id
                )
                if cancelled is not None:
                    return ProcessIncomingMessageResult(
                        type=(
                            IncomingMessageResultType
                            .GITHUB_VAULT_REPLACEMENT_CANCELLED
                        ),
                        app_user=app_user,
                        vault_selection=cancelled,
                    )
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_REBIND_CANCELLED
            )

        if self._user_identity_service.has_pending_rebind(identity):
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_REBIND_CONFIRMATION_PENDING
            )

        if text == "/start":
            app_user = self._user_identity_service.resolve(identity)
            if app_user is None:
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.START_UNREGISTERED
                )
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.START_REGISTERED,
                app_user=app_user,
            )

        if text == "/register":
            existing = self._user_identity_service.resolve(identity)
            if existing is not None:
                LOGGER.debug(
                    "User already registered: app_user_id=%s channel=%s "
                    "external_user_id=%s external_chat_id=%s username=%s",
                    existing.id,
                    identity.channel,
                    identity.external_user_id,
                    identity.external_chat_id,
                    identity.username,
                )
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.ALREADY_REGISTERED,
                    app_user=existing,
                )

            app_user = self._user_identity_service.register(identity)
            LOGGER.debug(
                "User registered: app_user_id=%s channel=%s "
                "external_user_id=%s external_chat_id=%s username=%s",
                app_user.id,
                identity.channel,
                identity.external_user_id,
                identity.external_chat_id,
                identity.username,
            )
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
            LOGGER.debug(
                "Identity link code created: app_user_id=%s expires_at=%s",
                app_user.id,
                link_code.expires_at.isoformat(),
            )
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
                LOGGER.debug(
                    "Identity linked: app_user_id=%s channel=%s external_user_id=%s "
                    "external_chat_id=%s username=%s",
                    app_user.id,
                    identity.channel,
                    identity.external_user_id,
                    identity.external_chat_id,
                    identity.username,
                )
                return ProcessIncomingMessageResult(
                    type=IncomingMessageResultType.LINKED,
                    app_user=app_user,
                )
            except IdentityAlreadyBoundError as error:
                try:
                    target_user = self._user_identity_service.request_rebind_confirmation(
                        code=parts[1],
                        identity=identity,
                    )
                    return ProcessIncomingMessageResult(
                        type=IncomingMessageResultType.LINK_REBIND_CONFIRMATION_REQUIRED,
                        app_user=target_user,
                    )
                except IdentityAlreadyBoundError:
                    return ProcessIncomingMessageResult(
                        type=IncomingMessageResultType.LINK_ALREADY_BOUND,
                        error=error,
                    )
                except InvalidLinkCodeError as rebind_error:
                    return ProcessIncomingMessageResult(
                        type=IncomingMessageResultType.LINK_CODE_INVALID,
                        error=rebind_error,
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
        if text == "/status":
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.STATUS,
                app_user=app_user,
            )
        if text == "/github_connect":
            return self._start_github_connection(
                app_user,
                github_completion_handler=github_completion_handler,
            )
        if text.startswith("/github_vault"):
            return self._select_github_vault(text, app_user)
        if text.startswith("/reanalyze"):
            return self._reanalyze_article(text, incoming_message, app_user)
        return app_user

    def _start_github_connection(
        self,
        app_user: AppUser,
        *,
        github_completion_handler: GitHubConnectionCompletionHandler | None,
    ) -> ProcessIncomingMessageResult:
        """Запускает общий для Telegram/VK GitHub Device Flow."""
        if self._github_connection_starter is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_UNAVAILABLE,
                app_user=app_user,
            )
        try:
            connection = self._github_connection_starter.start(
                app_user.id,
                github_completion_handler,
            )
        except (GitHubGatewayError, OSError, ValueError) as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_FAILED,
                app_user=app_user,
                error=error,
            )
        result_types = {
            GitHubConnectionStartStatus.STARTED: (
                IncomingMessageResultType.GITHUB_CONNECT_STARTED
            ),
            GitHubConnectionStartStatus.ALREADY_PENDING: (
                IncomingMessageResultType.GITHUB_CONNECT_ALREADY_PENDING
            ),
            GitHubConnectionStartStatus.PREPARING: (
                IncomingMessageResultType.GITHUB_CONNECT_PREPARING
            ),
            GitHubConnectionStartStatus.RECONNECT_CONFIRMATION_REQUIRED: (
                IncomingMessageResultType.GITHUB_RECONNECT_CONFIRMATION_REQUIRED
            ),
            GitHubConnectionStartStatus.IN_PROGRESS: (
                IncomingMessageResultType.GITHUB_CONNECT_IN_PROGRESS
            ),
        }
        return ProcessIncomingMessageResult(
            type=result_types[connection.status],
            app_user=app_user,
            github_connection=connection,
        )

    def _select_github_vault(
        self,
        text: str,
        app_user: AppUser,
    ) -> ProcessIncomingMessageResult:
        """Проверяет аргументы `/github_vault` и запускает выбор vault."""
        parts = text.split(maxsplit=2)
        if (
            len(parts) < 2
            or parts[0] != "/github_vault"
            or not parts[1].strip()
        ):
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_COMMAND_INVALID,
                app_user=app_user,
            )
        if self._vault_selection_manager is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_UNAVAILABLE,
                app_user=app_user,
            )
        try:
            selection = self._vault_selection_manager.select(
                app_user_id=app_user.id,
                repository_url=parts[1],
                root_path=parts[2] if len(parts) == 3 else "",
            )
        except GitHubAccountNotConnectedError as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_GITHUB_REQUIRED,
                app_user=app_user,
                error=error,
            )
        except GitHubRepositoryNotAccessibleError as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_REPOSITORY_UNAVAILABLE,
                app_user=app_user,
                error=error,
            )
        except GitHubVaultPathNotFoundError as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_PATH_NOT_FOUND,
                app_user=app_user,
                error=error,
            )
        except ValueError as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_COMMAND_INVALID,
                app_user=app_user,
                error=error,
            )
        except (GitHubGatewayError, OSError) as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_FAILED,
                app_user=app_user,
                error=error,
            )
        result_types = {
            VaultSelectionStatus.SELECTED: (
                IncomingMessageResultType.GITHUB_VAULT_SELECTED
            ),
            VaultSelectionStatus.ALREADY_SELECTED: (
                IncomingMessageResultType.GITHUB_VAULT_ALREADY_SELECTED
            ),
            VaultSelectionStatus.REPLACEMENT_CONFIRMATION_REQUIRED: (
                IncomingMessageResultType
                .GITHUB_VAULT_REPLACEMENT_CONFIRMATION_REQUIRED
            ),
        }
        return ProcessIncomingMessageResult(
            type=result_types[selection.status],
            app_user=app_user,
            vault_selection=selection,
        )

    def _confirm_vault_replacement(
        self,
        app_user: AppUser,
    ) -> ProcessIncomingMessageResult:
        """Применяет ожидающую замену vault после ответа `да`."""
        if self._vault_selection_manager is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_UNAVAILABLE,
                app_user=app_user,
            )
        try:
            selection = self._vault_selection_manager.confirm_replacement(app_user.id)
        except (OSError, ValueError) as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_FAILED,
                app_user=app_user,
                error=error,
            )
        if selection is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_CONFIRMATION_MISSING,
                app_user=app_user,
            )
        return ProcessIncomingMessageResult(
            type=IncomingMessageResultType.GITHUB_VAULT_REPLACED,
            app_user=app_user,
            vault_selection=selection,
        )

    def _confirm_github_reconnect(
        self,
        app_user: AppUser,
        *,
        github_completion_handler: GitHubConnectionCompletionHandler | None,
    ) -> ProcessIncomingMessageResult:
        """Подтверждает замену GitHub-аккаунта и возвращает новый challenge."""
        if self._github_connection_starter is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_UNAVAILABLE,
                app_user=app_user,
            )
        try:
            connection = self._github_connection_starter.confirm_reconnect(
                app_user.id,
                github_completion_handler,
            )
        except (GitHubGatewayError, OSError, ValueError) as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_FAILED,
                app_user=app_user,
                error=error,
            )
        if connection is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_RECONNECT_CONFIRMATION_MISSING,
                app_user=app_user,
            )
        result_types = {
            GitHubConnectionStartStatus.STARTED: (
                IncomingMessageResultType.GITHUB_CONNECT_STARTED
            ),
            GitHubConnectionStartStatus.ALREADY_PENDING: (
                IncomingMessageResultType.GITHUB_CONNECT_ALREADY_PENDING
            ),
            GitHubConnectionStartStatus.PREPARING: (
                IncomingMessageResultType.GITHUB_CONNECT_PREPARING
            ),
            GitHubConnectionStartStatus.IN_PROGRESS: (
                IncomingMessageResultType.GITHUB_CONNECT_IN_PROGRESS
            ),
        }
        return ProcessIncomingMessageResult(
            type=result_types[connection.status],
            app_user=app_user,
            github_connection=connection,
        )

    def _reanalyze_article(
        self,
        text: str,
        incoming_message: IncomingMessage,
        app_user: AppUser,
    ) -> ProcessIncomingMessageResult:
        """Повторно анализирует сохранённую статью по команде пользователя."""
        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip() or not parts[1].strip().isdigit():
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.REANALYZE_COMMAND_INVALID,
                app_user=app_user,
            )
        if self._article_analysis_use_case is None:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_REANALYSIS_FAILED,
                app_user=app_user,
                error=AnalyzeArticleError("Article analysis use case is not configured"),
            )

        try:
            analysis_result = self._article_analysis_use_case.execute(
                AnalyzeArticleCommand(
                    article_id=int(parts[1]),
                    app_user_id=app_user.id,
                    incoming_message_id=None,
                    force=True,
                )
            )
        except AnalyzeArticleError as error:
            return ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_REANALYSIS_FAILED,
                app_user=app_user,
                error=error,
            )

        return ProcessIncomingMessageResult(
            type=IncomingMessageResultType.ARTICLE_REANALYZED,
            app_user=app_user,
            analysis_result=analysis_result,
        )

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


def _text_kind(text: str) -> str:
    stripped_text = text.strip()
    if not stripped_text:
        return "empty"
    if stripped_text.startswith("/"):
        command = stripped_text.split(maxsplit=1)[0]
        return f"command:{command}"
    if extract_first_supported_url(stripped_text) is not None:
        return "url"
    return "text"


def _log_result(result: ProcessIncomingMessageResult) -> None:
    LOGGER.debug(
        "Incoming message processed: result=%s app_user_id=%s "
        "incoming_message_id=%s article_id=%s analysis_id=%s error_type=%s",
        result.type.value,
        result.app_user.id if result.app_user is not None else None,
        result.saved_message.id if result.saved_message is not None else None,
        (
            result.article_result.article.id
            if result.article_result is not None
            else None
        ),
        (
            result.analysis_result.analysis.id
            if result.analysis_result is not None
            else None
        ),
        type(result.error).__name__ if result.error is not None else None,
    )
