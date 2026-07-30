"""Тесты общего application-flow входящих сообщений."""

import unittest

from obs_chat_bot.application.articles.incoming_messages import (
    IncomingMessage,
    SavedIncomingMessage,
)
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlResult,
)
from obs_chat_bot.application.articles.analysis import (
    AnalyzeArticleCommand,
    AnalyzeArticleResult,
)
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageUseCase,
)
from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionCompletion,
    GitHubConnectionCompletionStatus,
    GitHubConnectionStartResult,
    GitHubConnectionStartStatus,
    GitHubDeviceAuthorization,
    GitHubGatewayError,
)
from obs_chat_bot.application.vaults.vault_selection import (
    GitHubAccountNotConnectedError,
    VaultDisconnectResult,
    VaultDisconnectStatus,
    VaultSelectionResult,
    VaultSelectionStatus,
)
from obs_chat_bot.application.vaults.vault_configuration import (
    VaultConfigurationError,
    VaultConfigurationErrorCode,
)
from obs_chat_bot.application.vaults.vault_sync import (
    VaultStatus,
    VaultSyncResult,
    VaultSyncStatus,
    VaultSyncWarningReason,
)
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.analysis import ArticleAnalysisResult
from obs_chat_bot.domain.articles.statuses import ArticleStatus
from obs_chat_bot.application.users.identity import IdentityAlreadyBoundError
from obs_chat_bot.domain.users.entities import AppUser, IncomingIdentity
from obs_chat_bot.domain.vaults.entities import ObsidianVault


class FakeArticleUrlUseCase:
    """Fake use case обработки URL для общего incoming-flow."""

    def __init__(self) -> None:
        self.commands: list[ProcessArticleUrlCommand] = []

    def execute(self, command: ProcessArticleUrlCommand) -> ProcessArticleUrlResult:
        """Возвращает успешный результат обработки статьи."""
        self.commands.append(command)
        return ProcessArticleUrlResult(
            article=Article(
                id=7,
                app_user_id=command.app_user_id,
                source_url=command.source_url,
                normalized_url=command.source_url,
                title="Article title",
                cleaned_text="Clean text",
                status=ArticleStatus.EXTRACTED,
            ),
            created=True,
            extracted=True,
        )


class FakeIncomingMessageRepository:
    """Fake repository входящих сообщений для общего incoming-flow."""

    def __init__(self) -> None:
        self.messages: list[IncomingMessage] = []
        self.links: list[tuple[int, int]] = []

    def save(self, message: IncomingMessage) -> SavedIncomingMessage:
        """Сохраняет сообщение в памяти."""
        self.messages.append(message)
        return SavedIncomingMessage(
            id=len(self.messages),
            app_user_id=message.app_user_id,
            channel=message.channel,
            chat_id=message.chat_id,
            message_id=message.message_id,
            text=message.text,
        )

    def link_to_article(
        self,
        *,
        incoming_message_id: int,
        article_id: int,
    ) -> SavedIncomingMessage | None:
        """Запоминает связь сообщения со статьей."""
        self.links.append((incoming_message_id, article_id))
        message = self.messages[incoming_message_id - 1]
        return SavedIncomingMessage(
            id=incoming_message_id,
            app_user_id=message.app_user_id,
            channel=message.channel,
            chat_id=message.chat_id,
            message_id=message.message_id,
            text=message.text,
            article_id=article_id,
        )


class FakeAnalysisUseCase:
    """Fake use case LLM-анализа для общего incoming-flow."""

    def __init__(self) -> None:
        self.commands: list[AnalyzeArticleCommand] = []

    def execute(self, command: AnalyzeArticleCommand) -> AnalyzeArticleResult:
        """Запоминает команду и возвращает новый анализ."""
        self.commands.append(command)
        article = Article(
            id=command.article_id,
            app_user_id=command.app_user_id,
            source_url="https://example.com/article",
            normalized_url="https://example.com/article",
            title="Article title",
            cleaned_text="Clean text",
            status=ArticleStatus.ANALYZED,
        )
        return AnalyzeArticleResult(
            article=article,
            analysis=ArticleAnalysisResult(
                id=3,
                app_user_id=command.app_user_id,
                article_id=command.article_id,
                llm_model="fake-llm",
                prompt_version="article-summary-v1",
                result_text="## Кратко\nНовый анализ.",
            ),
            created=True,
        )


class FakeUserIdentityService:
    """Fake identity service для команд зарегистрированного пользователя."""

    def __init__(self) -> None:
        self.app_user = AppUser(id=42, display_name="Test User")

    def resolve(self, _identity: IncomingIdentity) -> AppUser | None:
        """Всегда возвращает пользователя."""
        return self.app_user

    def has_pending_rebind(self, _identity: IncomingIdentity) -> bool:
        """По умолчанию pending-перепривязки нет."""
        return False

    def confirm_rebind(self, _identity: IncomingIdentity) -> AppUser:
        """Возвращает пользователя для тестов подтверждения перепривязки."""
        return self.app_user

    def cancel_rebind(self, _identity: IncomingIdentity) -> None:
        """Запоминает отмену перепривязки."""

    def update_display_name(
        self,
        *,
        app_user_id: int,
        display_name: str,
    ) -> AppUser:
        """Обновляет тестовое имя пользователя."""
        self.app_user = AppUser(
            id=app_user_id,
            display_name=" ".join(display_name.split()),
        )
        return self.app_user


class FakeRebindIdentityService(FakeUserIdentityService):
    """Fake identity service для проверки подтверждения перепривязки."""

    def __init__(self) -> None:
        super().__init__()
        self.target_user = AppUser(id=99, display_name="Target User")
        self.rebind_requested = False
        self.rebind_confirmed = False
        self.rebind_cancelled = False
        self.pending_rebind = False

    def link(self, *, code: str, identity: IncomingIdentity) -> AppUser:
        """Имитирует попытку привязать уже связанный канал."""
        raise IdentityAlreadyBoundError("External identity is already bound")

    def request_rebind_confirmation(
        self,
        *,
        code: str,
        identity: IncomingIdentity,
    ) -> AppUser:
        """Имитирует создание ожидающего подтверждения перепривязки."""
        self.rebind_requested = True
        self.pending_rebind = True
        return self.target_user

    def has_pending_rebind(self, _identity: IncomingIdentity) -> bool:
        """Возвращает состояние ожидающего подтверждения."""
        return self.pending_rebind

    def confirm_rebind(self, _identity: IncomingIdentity) -> AppUser:
        """Имитирует подтвержденную перепривязку."""
        self.rebind_confirmed = True
        self.pending_rebind = False
        return self.target_user

    def cancel_rebind(self, _identity: IncomingIdentity) -> None:
        """Имитирует отмену перепривязки."""
        self.rebind_cancelled = True
        self.pending_rebind = False


class FakeRegisteringIdentityService:
    """Fake identity service для проверки регистрации и `/start`."""

    def __init__(self, existing: AppUser | None = None) -> None:
        self.app_user = existing or AppUser(id=77)
        self.register_calls = 0
        self._existing = existing

    def resolve(self, _identity: IncomingIdentity) -> AppUser | None:
        """Возвращает существующего пользователя, если он задан."""
        return self._existing

    def has_pending_rebind(self, _identity: IncomingIdentity) -> bool:
        """В тестах регистрации pending-перепривязки нет."""
        return False

    def register(self, _identity: IncomingIdentity) -> AppUser:
        """Создает пользователя и запоминает регистрацию."""
        self.register_calls += 1
        self._existing = self.app_user
        return self.app_user

    def update_display_name(
        self,
        *,
        app_user_id: int,
        display_name: str,
    ) -> AppUser:
        """Сохраняет тестовое имя после регистрации."""
        self.app_user = AppUser(
            id=app_user_id,
            display_name=" ".join(display_name.split()),
        )
        self._existing = self.app_user
        return self.app_user


class FakeGitHubConnectionStarter:
    """Возвращает предсказуемый Device Flow challenge."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.app_user_ids: list[int] = []
        self.completion_handler = None

    @property
    def installation_url(self) -> str:
        """Возвращает тестовую страницу установки App."""
        return "https://github.com/apps/obs-chat-bot/installations/new"

    def start(
        self,
        app_user_id: int,
        _completion_handler=None,
    ) -> GitHubConnectionStartResult:
        """Запоминает пользователя или поднимает настроенную ошибку."""
        self.app_user_ids.append(app_user_id)
        self.completion_handler = _completion_handler
        if self.error is not None:
            raise self.error
        return GitHubConnectionStartResult(
            status=GitHubConnectionStartStatus.STARTED,
            installation_url=(
                "https://github.com/apps/obs-chat-bot/installations/new"
            ),
            authorization=GitHubDeviceAuthorization(
                device_code="device-secret",
                user_code="ABCD-EFGH",
                verification_uri="https://github.com/login/device",
                expires_in=900,
                interval=5,
            ),
        )


class FakeVaultSelectionManager:
    """Имитирует выбор и подтверждаемую замену Obsidian vault."""

    def __init__(
        self,
        status: VaultSelectionStatus = VaultSelectionStatus.SELECTED,
        *,
        error: Exception | None = None,
        selected: ObsidianVault | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.selected = selected
        self.calls: list[tuple[int, str, str]] = []
        self.replacement_pending = False
        self.disconnect_pending = False

    def get_selected(self, _app_user_id: int) -> ObsidianVault | None:
        """Возвращает настроенный активный vault."""
        return self.selected

    def select(
        self,
        *,
        app_user_id: int,
        repository_url: str,
        root_path: str = "",
    ) -> VaultSelectionResult:
        """Запоминает команду и возвращает настроенный результат."""
        self.calls.append((app_user_id, repository_url, root_path))
        if self.error is not None:
            raise self.error
        self.replacement_pending = (
            self.status is VaultSelectionStatus.REPLACEMENT_CONFIRMATION_REQUIRED
        )
        vault = _test_vault(app_user_id)
        if self.status in {
            VaultSelectionStatus.SELECTED,
            VaultSelectionStatus.ALREADY_SELECTED,
        }:
            self.selected = vault
        return VaultSelectionResult(self.status, vault)

    def has_replacement_confirmation(self, _app_user_id: int) -> bool:
        """Возвращает состояние ожидающей замены."""
        return self.replacement_pending

    def confirm_replacement(
        self,
        app_user_id: int,
    ) -> VaultSelectionResult | None:
        """Подтверждает настроенную ожидающую замену."""
        if not self.replacement_pending:
            return None
        self.replacement_pending = False
        return VaultSelectionResult(
            VaultSelectionStatus.REPLACED,
            _test_vault(app_user_id),
        )

    def cancel_replacement(
        self,
        app_user_id: int,
    ) -> VaultSelectionResult | None:
        """Отменяет настроенную ожидающую замену."""
        if not self.replacement_pending:
            return None
        self.replacement_pending = False
        return VaultSelectionResult(
            VaultSelectionStatus.CANCELLED,
            _test_vault(app_user_id),
        )

    def request_disconnect(self, app_user_id: int) -> VaultDisconnectResult:
        """Запрашивает тестовое подтверждение отключения."""
        if self.selected is None:
            return VaultDisconnectResult(VaultDisconnectStatus.NOT_CONNECTED)
        self.disconnect_pending = True
        return VaultDisconnectResult(
            VaultDisconnectStatus.CONFIRMATION_REQUIRED,
            self.selected,
        )

    def has_disconnect_confirmation(self, _app_user_id: int) -> bool:
        """Возвращает состояние ожидающего отключения."""
        return self.disconnect_pending

    def confirm_disconnect(
        self,
        app_user_id: int,
    ) -> VaultDisconnectResult | None:
        """Подтверждает тестовое отключение."""
        if not self.disconnect_pending:
            return None
        self.disconnect_pending = False
        vault = self.selected or _test_vault(app_user_id)
        self.selected = None
        return VaultDisconnectResult(VaultDisconnectStatus.DISCONNECTED, vault)

    def cancel_disconnect(
        self,
        app_user_id: int,
    ) -> VaultDisconnectResult | None:
        """Отменяет тестовое отключение."""
        if not self.disconnect_pending:
            return None
        self.disconnect_pending = False
        return VaultDisconnectResult(
            VaultDisconnectStatus.CANCELLED,
            self.selected or _test_vault(app_user_id),
        )


class FakeVaultSyncManager:
    """Имитирует ручную и ленивую синхронизацию vault."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        status: VaultSyncStatus = VaultSyncStatus.FRESH,
    ) -> None:
        self.error = error
        self.status = status
        self.auto_calls: list[int] = []

    def sync(self, app_user_id: int) -> VaultSyncResult:
        """Возвращает успешную ручную проверку."""
        return VaultSyncResult(
            status=VaultSyncStatus.UNCHANGED,
            vault=_test_vault(app_user_id),
        )

    def sync_if_stale(self, app_user_id: int) -> VaultSyncResult:
        """Запоминает автоматическую проверку либо поднимает ошибку."""
        self.auto_calls.append(app_user_id)
        if self.error is not None:
            raise self.error
        return VaultSyncResult(
            status=self.status,
            vault=_test_vault(app_user_id),
            total_notes=3,
        )

    def get_status(self, app_user_id: int) -> VaultStatus:
        """Возвращает тестовый статус подключённого vault."""
        return VaultStatus(vault=_test_vault(app_user_id), note_count=3)


class ProcessIncomingMessageUseCaseTest(unittest.TestCase):
    """Проверяет общий application-flow без Telegram adapter."""

    def test_execute_help_is_available_without_registered_identity(self) -> None:
        """`/help` возвращает список команд до регистрации пользователя."""
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeRegisteringIdentityService(),
        )

        result = use_case.execute(_telegram_message("/help"))

        self.assertEqual(result.type, IncomingMessageResultType.HELP)
        self.assertIsNone(result.app_user)

    def test_execute_processes_url_and_links_saved_message(self) -> None:
        """Сообщение со ссылкой проходит общий flow и возвращает structured result."""
        article_use_case = FakeArticleUrlUseCase()
        message_repository = FakeIncomingMessageRepository()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            incoming_message_repository=message_repository,
        )

        result = use_case.execute(
            IncomingMessage(
                app_user_id=5,
                channel="vk",
                chat_id="chat-1",
                message_id="msg-1",
                text="https://example.com/article",
            )
        )

        self.assertEqual(result.type, IncomingMessageResultType.ARTICLE_PROCESSED)
        self.assertEqual(article_use_case.commands[0].app_user_id, 5)
        self.assertEqual(article_use_case.commands[0].incoming_message_id, 1)
        self.assertEqual(message_repository.messages[0].app_user_id, 5)
        self.assertEqual(message_repository.links, [(1, 7)])

    def test_execute_checks_stale_vault_before_article_in_common_flow(self) -> None:
        """Telegram/VK-независимый flow проверяет vault до article use case."""
        article_use_case = FakeArticleUrlUseCase()
        sync_manager = FakeVaultSyncManager()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            user_identity_service=FakeUserIdentityService(),
            vault_sync_manager=sync_manager,
        )

        result = use_case.execute(
            _telegram_message("https://example.com/article")
        )

        self.assertEqual(sync_manager.auto_calls, [42])
        self.assertEqual(len(article_use_case.commands), 1)
        self.assertEqual(result.vault_sync_result.status, VaultSyncStatus.FRESH)

    def test_execute_uses_local_vault_when_automatic_github_check_fails(self) -> None:
        """Сбой GitHub не останавливает статью и возвращает предупреждение."""
        article_use_case = FakeArticleUrlUseCase()
        sync_manager = FakeVaultSyncManager(
            error=GitHubGatewayError("GitHub request failed with HTTP 503")
        )
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            user_identity_service=FakeUserIdentityService(),
            vault_sync_manager=sync_manager,
        )

        result = use_case.execute(
            _telegram_message("https://example.com/article")
        )

        self.assertEqual(result.type, IncomingMessageResultType.ARTICLE_PROCESSED)
        self.assertEqual(len(article_use_case.commands), 1)
        self.assertIsNone(result.error)
        self.assertEqual(
            result.vault_sync_warning.reason,
            VaultSyncWarningReason.UPDATE_FAILED,
        )
        self.assertEqual(result.vault_sync_warning.note_count, 3)

    def test_execute_stops_article_when_vault_configuration_is_missing(
        self,
    ) -> None:
        """Ошибка обязательной конфигурации не маскируется GitHub fallback."""
        article_use_case = FakeArticleUrlUseCase()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            user_identity_service=FakeUserIdentityService(),
            vault_sync_manager=FakeVaultSyncManager(
                error=VaultConfigurationError(
                    VaultConfigurationErrorCode.MISSING
                )
            ),
        )

        result = use_case.execute(
            _telegram_message("https://example.com/article")
        )

        self.assertEqual(
            result.type,
            IncomingMessageResultType.GITHUB_VAULT_CONFIGURATION_REQUIRED,
        )
        self.assertEqual(article_use_case.commands, [])

    def test_execute_uses_local_vault_while_other_channel_syncs(self) -> None:
        """Активный lease не останавливает статью и объясняется предупреждением."""
        article_use_case = FakeArticleUrlUseCase()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            user_identity_service=FakeUserIdentityService(),
            vault_sync_manager=FakeVaultSyncManager(
                status=VaultSyncStatus.IN_PROGRESS
            ),
        )

        result = use_case.execute(
            _telegram_message("https://example.com/article")
        )

        self.assertEqual(result.type, IncomingMessageResultType.ARTICLE_PROCESSED)
        self.assertEqual(len(article_use_case.commands), 1)
        self.assertIsNone(result.error)
        self.assertEqual(
            result.vault_sync_warning.reason,
            VaultSyncWarningReason.IN_PROGRESS,
        )
        self.assertEqual(result.vault_sync_warning.note_count, 3)

    def test_execute_returns_missing_url_without_saving_message(self) -> None:
        """Сообщение без URL не сохраняется и возвращает structured result."""
        message_repository = FakeIncomingMessageRepository()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            incoming_message_repository=message_repository,
        )

        result = use_case.execute(
            IncomingMessage(
                channel="vk",
                chat_id="chat-1",
                message_id="msg-1",
                text="hello",
            )
        )

        self.assertEqual(result.type, IncomingMessageResultType.ARTICLE_URL_MISSING)
        self.assertEqual(message_repository.messages, [])

    def test_execute_returns_status_for_registered_identity(self) -> None:
        """Команда `/status` возвращает structured result текущего пользователя."""
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
        )

        result = use_case.execute(_telegram_message("/status"))

        self.assertEqual(result.type, IncomingMessageResultType.STATUS)
        self.assertEqual(result.app_user.id, 42)

    def test_repository_url_starts_github_authorization_when_account_is_missing(
        self,
    ) -> None:
        """Repository URL запускает Device Flow для внутреннего app_user."""
        starter = FakeGitHubConnectionStarter()
        manager = FakeVaultSelectionManager(
            error=GitHubAccountNotConnectedError("GitHub is not authorized")
        )
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            github_connection_starter=starter,
            vault_selection_manager=manager,
        )

        result = use_case.execute(
            _telegram_message("https://github.com/octocat/notes")
        )

        self.assertEqual(result.type, IncomingMessageResultType.GITHUB_CONNECT_STARTED)
        self.assertEqual(result.github_connection.authorization.user_code, "ABCD-EFGH")
        self.assertEqual(starter.app_user_ids, [42])

    def test_execute_reports_unconfigured_github_connector(self) -> None:
        """Repository URL сообщает об отключённой GitHub App конфигурации."""
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            vault_selection_manager=FakeVaultSelectionManager(
                error=GitHubAccountNotConnectedError("GitHub is not authorized")
            ),
        )

        result = use_case.execute(
            _telegram_message("https://github.com/octocat/notes")
        )

        self.assertEqual(
            result.type,
            IncomingMessageResultType.GITHUB_CONNECT_UNAVAILABLE,
        )

    def test_execute_selects_github_vault_for_shared_app_user(self) -> None:
        """Обычная GitHub-ссылка передаёт repository и path общему сервису."""
        manager = FakeVaultSelectionManager()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            vault_selection_manager=manager,
        )

        result = use_case.execute(
            _telegram_message(
                "https://github.com/octocat/notes Vault/Personal"
            )
        )

        self.assertEqual(result.type, IncomingMessageResultType.GITHUB_VAULT_SELECTED)
        self.assertEqual(
            manager.calls,
            [(42, "https://github.com/octocat/notes", "Vault/Personal")],
        )

    def test_execute_confirms_and_cancels_vault_replacement(self) -> None:
        """Ответы `да` и `нет` управляют pending vault по `app_user_id`."""
        manager = FakeVaultSelectionManager(
            VaultSelectionStatus.REPLACEMENT_CONFIRMATION_REQUIRED
        )
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            vault_selection_manager=manager,
        )
        pending = use_case.execute(
            _telegram_message("https://github.com/octocat/second")
        )
        confirmed = use_case.execute(_telegram_message("да"))

        manager.replacement_pending = True
        cancelled = use_case.execute(_telegram_message("нет"))

        self.assertEqual(
            pending.type,
            IncomingMessageResultType
            .GITHUB_VAULT_REPLACEMENT_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(
            confirmed.type,
            IncomingMessageResultType.GITHUB_VAULT_REPLACED,
        )
        self.assertEqual(
            cancelled.type,
            IncomingMessageResultType.GITHUB_VAULT_REPLACEMENT_CANCELLED,
        )

    def test_execute_disconnects_vault_only_after_confirmation(self) -> None:
        """Команда создаёт подтверждение, `нет` отменяет, а `да` удаляет vault."""
        manager = FakeVaultSelectionManager(selected=_test_vault(42))
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            vault_selection_manager=manager,
        )

        requested = use_case.execute(_telegram_message("/github_disconnect"))
        cancelled = use_case.execute(_telegram_message("нет"))
        use_case.execute(_telegram_message("/github_disconnect"))
        confirmed = use_case.execute(_telegram_message("да"))

        self.assertEqual(
            requested.type,
            IncomingMessageResultType.GITHUB_DISCONNECT_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(
            cancelled.type,
            IncomingMessageResultType.GITHUB_DISCONNECT_CANCELLED,
        )
        self.assertEqual(
            confirmed.type,
            IncomingMessageResultType.GITHUB_DISCONNECTED,
        )
        self.assertIsNone(manager.selected)

    def test_execute_disconnect_reports_missing_vault(self) -> None:
        """Команда без активного vault не создаёт подтверждение."""
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            vault_selection_manager=FakeVaultSelectionManager(),
        )

        result = use_case.execute(_telegram_message("/github_disconnect"))

        self.assertEqual(
            result.type,
            IncomingMessageResultType.GITHUB_DISCONNECT_NOT_CONNECTED,
        )

    def test_execute_hides_github_gateway_failure_behind_typed_result(self) -> None:
        """Сетевая ошибка GitHub не запускает article pipeline."""
        starter = FakeGitHubConnectionStarter(
            error=GitHubGatewayError("GitHub request failed with HTTP 503")
        )
        article_use_case = FakeArticleUrlUseCase()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            user_identity_service=FakeUserIdentityService(),
            github_connection_starter=starter,
            vault_selection_manager=FakeVaultSelectionManager(
                error=GitHubAccountNotConnectedError("GitHub is not authorized")
            ),
        )

        result = use_case.execute(
            _telegram_message("https://github.com/octocat/notes")
        )

        self.assertEqual(result.type, IncomingMessageResultType.GITHUB_CONNECT_FAILED)
        self.assertEqual(article_use_case.commands, [])

    def test_authorization_completion_continues_original_vault_selection(self) -> None:
        """После Device Flow бот автоматически продолжает исходный repository."""
        starter = FakeGitHubConnectionStarter()
        manager = FakeVaultSelectionManager(
            error=GitHubAccountNotConnectedError("GitHub is not authorized")
        )
        completions = []
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            github_connection_starter=starter,
            vault_selection_manager=manager,
        )

        started = use_case.execute(
            _telegram_message("https://github.com/octocat/notes Vault"),
            completions.append,
        )
        manager.error = None
        starter.completion_handler(
            GitHubConnectionCompletion(
                GitHubConnectionCompletionStatus.CONNECTED,
                installation_count=1,
                account_login="octocat",
            )
        )

        self.assertEqual(started.type, IncomingMessageResultType.GITHUB_CONNECT_STARTED)
        self.assertEqual(
            completions[0].type,
            IncomingMessageResultType.GITHUB_VAULT_SELECTED,
        )
        self.assertEqual(
            manager.calls[-1],
            (42, "https://github.com/octocat/notes", "Vault"),
        )

    def test_authorization_without_installation_requests_app_setup(self) -> None:
        """После Device Flow без installation бот даёт ссылку настройки App."""
        starter = FakeGitHubConnectionStarter()
        manager = FakeVaultSelectionManager(
            error=GitHubAccountNotConnectedError("GitHub is not authorized")
        )
        completions = []
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            github_connection_starter=starter,
            vault_selection_manager=manager,
        )

        use_case.execute(
            _telegram_message("https://github.com/octocat/notes"),
            completions.append,
        )
        starter.completion_handler(
            GitHubConnectionCompletion(
                GitHubConnectionCompletionStatus.NO_INSTALLATIONS
            )
        )

        self.assertEqual(
            completions[0].type,
            IncomingMessageResultType.GITHUB_APP_REQUIRED,
        )
        self.assertEqual(
            completions[0].installation_url,
            starter.installation_url,
        )

    def test_article_is_blocked_until_registration_has_vault(self) -> None:
        """Статьи не обрабатываются до завершения подключения Obsidian vault."""
        article_use_case = FakeArticleUrlUseCase()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            user_identity_service=FakeUserIdentityService(),
            vault_selection_manager=FakeVaultSelectionManager(),
        )

        result = use_case.execute(
            _telegram_message("https://example.com/article")
        )

        self.assertEqual(
            result.type,
            IncomingMessageResultType.REGISTRATION_VAULT_REQUIRED,
        )
        self.assertEqual(article_use_case.commands, [])

    def test_execute_registers_new_identity(self) -> None:
        """Команда `/register` создаёт пользователя и запрашивает имя."""
        identity_service = FakeRegisteringIdentityService()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("/register"))

        self.assertEqual(result.type, IncomingMessageResultType.REGISTERED)
        self.assertEqual(result.app_user.id, 77)
        self.assertIsNone(result.app_user.display_name)
        self.assertEqual(identity_service.register_calls, 1)

    def test_execute_saves_registration_name_before_vault(self) -> None:
        """Обычный текст после `/register` становится общим именем профиля."""
        identity_service = FakeRegisteringIdentityService()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
            vault_selection_manager=FakeVaultSelectionManager(),
        )

        use_case.execute(_telegram_message("/register"))
        result = use_case.execute(_telegram_message("  Влад   Ерофеев  "))

        self.assertEqual(
            result.type,
            IncomingMessageResultType.REGISTRATION_NAME_SAVED,
        )
        self.assertEqual(result.app_user.display_name, "Влад Ерофеев")
        self.assertIsNone(result.selected_vault)

    def test_execute_saves_name_without_reselecting_existing_vault(self) -> None:
        """Переходный профиль с vault завершает onboarding только вводом имени."""
        identity_service = FakeRegisteringIdentityService(existing=AppUser(id=42))
        selected_vault = _test_vault(42)
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
            vault_selection_manager=FakeVaultSelectionManager(
                selected=selected_vault
            ),
        )

        result = use_case.execute(_telegram_message("Влад"))

        self.assertEqual(
            result.type,
            IncomingMessageResultType.REGISTRATION_NAME_SAVED,
        )
        self.assertEqual(result.selected_vault, selected_vault)

    def test_execute_name_command_changes_profile_name(self) -> None:
        """`/name` меняет общее имя пользователя всех связанных каналов."""
        identity_service = FakeUserIdentityService()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("/name Влад"))

        self.assertEqual(result.type, IncomingMessageResultType.NAME_UPDATED)
        self.assertEqual(result.app_user.display_name, "Влад")

    def test_execute_no_without_confirmation_reports_missing_action(self) -> None:
        """`нет` без pending-действия не сообщает о несуществующей отмене."""
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeUserIdentityService(),
            vault_selection_manager=FakeVaultSelectionManager(
                selected=_test_vault(42)
            ),
        )

        result = use_case.execute(_telegram_message("нет"))

        self.assertEqual(
            result.type,
            IncomingMessageResultType.CONFIRMATION_MISSING,
        )

    def test_execute_reports_already_registered_identity(self) -> None:
        """Повторный `/register` не создает пользователя заново."""
        identity_service = FakeRegisteringIdentityService(
            existing=AppUser(id=42, display_name="Test User")
        )
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("/register"))

        self.assertEqual(result.type, IncomingMessageResultType.ALREADY_REGISTERED)
        self.assertEqual(result.app_user.id, 42)
        self.assertEqual(identity_service.register_calls, 0)

    def test_execute_start_reports_registered_identity(self) -> None:
        """`/start` для привязанного канала возвращает registered-start result."""
        identity_service = FakeRegisteringIdentityService(
            existing=AppUser(id=42, display_name="Test User")
        )
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("/start"))

        self.assertEqual(result.type, IncomingMessageResultType.START_REGISTERED)
        self.assertEqual(result.app_user.id, 42)

    def test_execute_start_reports_unknown_identity(self) -> None:
        """`/start` для нового канала возвращает onboarding result."""
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=FakeRegisteringIdentityService(),
        )

        result = use_case.execute(_telegram_message("/start"))

        self.assertEqual(result.type, IncomingMessageResultType.START_UNREGISTERED)

    def test_execute_link_requests_rebind_confirmation_for_bound_identity(self) -> None:
        """`/link <код>` для привязанного канала просит подтвердить перепривязку."""
        identity_service = FakeRebindIdentityService()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("/link ABC123"))

        self.assertEqual(
            result.type,
            IncomingMessageResultType.LINK_REBIND_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(result.app_user.id, 99)
        self.assertTrue(identity_service.rebind_requested)

    def test_execute_yes_confirms_pending_rebind(self) -> None:
        """Ответ `да` подтверждает ожидающую перепривязку канала."""
        identity_service = FakeRebindIdentityService()
        identity_service.pending_rebind = True
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("да"))

        self.assertEqual(result.type, IncomingMessageResultType.LINK_REBOUND)
        self.assertEqual(result.app_user.id, 99)
        self.assertTrue(identity_service.rebind_confirmed)

    def test_execute_no_cancels_pending_rebind(self) -> None:
        """Ответ `нет` отменяет ожидающую перепривязку канала."""
        identity_service = FakeRebindIdentityService()
        identity_service.pending_rebind = True
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("нет"))

        self.assertEqual(result.type, IncomingMessageResultType.LINK_REBIND_CANCELLED)
        self.assertTrue(identity_service.rebind_cancelled)

    def test_execute_waits_for_yes_or_no_when_rebind_is_pending(self) -> None:
        """Произвольный текст при pending-перепривязке не уходит в article-flow."""
        identity_service = FakeRebindIdentityService()
        identity_service.pending_rebind = True
        article_use_case = FakeArticleUrlUseCase()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=article_use_case,
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("потом"))

        self.assertEqual(
            result.type,
            IncomingMessageResultType.LINK_REBIND_CONFIRMATION_PENDING,
        )
        self.assertEqual(article_use_case.commands, [])

    def test_execute_reanalyze_forces_article_analysis(self) -> None:
        """Команда `/reanalyze` запускает анализ с force=True."""
        analysis_use_case = FakeAnalysisUseCase()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            article_analysis_use_case=analysis_use_case,
            user_identity_service=FakeUserIdentityService(),
        )

        result = use_case.execute(_telegram_message("/reanalyze 7"))

        self.assertEqual(result.type, IncomingMessageResultType.ARTICLE_REANALYZED)
        self.assertEqual(analysis_use_case.commands[0].article_id, 7)
        self.assertEqual(analysis_use_case.commands[0].app_user_id, 42)
        self.assertTrue(analysis_use_case.commands[0].force)


def _telegram_message(text: str) -> IncomingMessage:
    """Создаёт входящее Telegram-сообщение для команд incoming-flow."""
    return IncomingMessage(
        channel="telegram",
        chat_id="chat-1",
        message_id="msg-1",
        external_user_id="user-1",
        text=text,
    )


def _test_vault(app_user_id: int) -> ObsidianVault:
    """Создаёт выбранный vault для incoming-flow тестов."""
    return ObsidianVault(
        id=1,
        app_user_id=app_user_id,
        installation_id=101,
        repository_id=501,
        owner="octocat",
        repository="notes",
        branch="main",
        root_path="Vault",
    )


if __name__ == "__main__":
    unittest.main()
