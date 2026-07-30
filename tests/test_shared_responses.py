"""Тесты форматирования общих ответов presentation-слоя."""

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from obs_chat_bot.application.articles.analysis import AnalyzeArticleResult
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlError,
    ProcessArticleUrlResult,
)
from obs_chat_bot.application.articles.stages import ProcessingStage
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageResult,
)
from obs_chat_bot.application.incoming.commands import ChatCommand
from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionCompletion,
    GitHubConnectionCompletionStatus,
    GitHubConnectionStartResult,
    GitHubConnectionStartStatus,
    GitHubDeviceAuthorization,
)
from obs_chat_bot.application.vaults.vault_selection import (
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
    VaultSyncWarning,
    VaultSyncWarningReason,
)
from obs_chat_bot.application.users.identity import CreatedLinkCode
from obs_chat_bot.domain.articles.analysis import ArticleAnalysisResult
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus
from obs_chat_bot.domain.users.entities import AppUser
from obs_chat_bot.domain.vaults.entities import ObsidianVault
from obs_chat_bot.presentation.shared.responses import (
    format_article_analysis_result,
    format_article_processing_result,
    format_incoming_message_result,
)


class TelegramResponsesTest(unittest.TestCase):
    """Проверяет пользовательский текст по результату обработки статьи."""

    def test_format_help_lists_only_currently_available_commands(self) -> None:
        """`/help` перечисляет общий набор реализованных Telegram/VK-команд."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(type=IncomingMessageResultType.HELP)
        )

        for command in ChatCommand:
            with self.subTest(command=command.value):
                self.assertIn(str(command), reply)
        self.assertIn("/github_sync", reply)
        self.assertIn("/github_status", reply)
        self.assertIn("/github_disconnect", reply)
        self.assertNotIn("/github_connect", reply)
        self.assertNotIn("/github_vault", reply)

    def test_format_missing_vault_configuration_includes_ready_example(
        self,
    ) -> None:
        """Ошибка первой синхронизации объясняет ручное создание YAML."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_SYNC_FAILED,
                error=VaultConfigurationError(
                    VaultConfigurationErrorCode.MISSING
                ),
            )
        )

        self.assertIn(".knowledge-catcher.yml", reply)
        self.assertIn("memory-bank/AGENTS.md.txt", reply)
        self.assertIn("```yaml", reply)

    def test_format_missing_instruction_names_required_path(self) -> None:
        """Ошибка перечисленного файла показывает исправляемый path."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_SYNC_FAILED,
                error=VaultConfigurationError(
                    VaultConfigurationErrorCode.INSTRUCTION_MISSING,
                    path="memory-bank/docs/workflows.md.txt",
                ),
            )
        )

        self.assertIn("memory-bank/docs/workflows.md.txt", reply)

    def test_format_article_processing_result_reports_created_article(self) -> None:
        """Новая статья получает понятный текст с названием, статусом, ID и длиной."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=_article(),
                created=True,
                extracted=True,
            )
        )

        self.assertIn("Готово: статья сохранена.", reply)
        self.assertIn("Название: Article title", reply)
        self.assertIn("Статус: текст извлечен", reply)
        self.assertIn("ID статьи: 1", reply)
        self.assertIn("Текст: 11 символов", reply)

    def test_format_article_processing_result_reports_existing_article(self) -> None:
        """Повторная ссылка получает отдельный текст без намека на новую запись."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=_article(),
                created=False,
                extracted=False,
            )
        )

        self.assertIn("Эта статья уже была сохранена.", reply)

    def test_format_article_processing_result_reports_updated_article(self) -> None:
        """Повторно извлеченная статья получает текст обновления."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=_article(),
                created=False,
                extracted=True,
            )
        )

        self.assertIn("Готово: статья обновлена.", reply)

    def test_format_article_processing_result_uses_fallbacks(self) -> None:
        """Ответ остается понятным, если у статьи нет заголовка или ID."""
        reply = format_article_processing_result(
            ProcessArticleUrlResult(
                article=replace(_article(), id=None, title=None, cleaned_text=None),
                created=True,
                extracted=False,
            )
        )

        self.assertIn("Название: без заголовка", reply)
        self.assertIn("ID статьи: не сохранен", reply)
        self.assertIn("Текст: 0 символов", reply)

    def test_format_article_analysis_result_includes_markdown_analysis(self) -> None:
        """Ответ с анализом содержит служебный контекст и Markdown LLM."""
        processing_result = ProcessArticleUrlResult(
            article=_article(),
            created=True,
            extracted=True,
        )
        analysis_result = AnalyzeArticleResult(
            article=replace(_article(), status=ArticleStatus.ANALYZED),
            analysis=ArticleAnalysisResult(
                id=1,
                article_id=1,
                llm_model="fake-llm",
                prompt_version="article-summary-v1",
                result_text="## Кратко\nГотовый анализ.",
            ),
            created=True,
        )

        reply = format_article_analysis_result(processing_result, analysis_result)

        self.assertIn("Готово: статья сохранена.", reply)
        self.assertIn("Анализ готов.", reply)
        self.assertIn("## Кратко", reply)


    def test_format_incoming_message_result_reports_missing_url(self) -> None:
        """Общий результат без URL получает пользовательскую подсказку."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_URL_MISSING
            )
        )

        self.assertIn("Пришли ссылку", reply)

    def test_format_incoming_message_result_reports_start_registered(self) -> None:
        """`/start` приветствует зарегистрированного пользователя по имени."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.START_REGISTERED,
                app_user=AppUser(id=42, display_name="Влад"),
            )
        )

        self.assertIn("Влад", reply)
        self.assertNotIn("42", reply)

    def test_format_incoming_message_result_reports_start_unregistered(self) -> None:
        """`/start` для нового канала объясняет регистрацию и привязку."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.START_UNREGISTERED,
            )
        )

        self.assertIn("пока не зарегистрирован", reply)
        self.assertIn("/register", reply)

    def test_format_incoming_message_result_reports_already_registered(self) -> None:
        """Повторный `/register` получает честный ответ."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ALREADY_REGISTERED,
                app_user=AppUser(id=42, display_name="Влад"),
                selected_vault=ObsidianVault(
                    id=1,
                    app_user_id=42,
                    installation_id=10,
                    repository_id=20,
                    owner="karateka-git",
                    repository="my_obs_data",
                    branch="main",
                ),
            )
        )

        self.assertIn("уже зарегистрирован", reply)
        self.assertIn("Влад", reply)
        self.assertIn("karateka-git/my_obs_data", reply)
        self.assertNotIn("42", reply)

    def test_name_completion_preserves_existing_vault(self) -> None:
        """После ввода имени уже подключённый vault не требуется выбирать снова."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.REGISTRATION_NAME_SAVED,
                app_user=AppUser(id=42, display_name="Влад"),
                selected_vault=ObsidianVault(
                    id=1,
                    app_user_id=42,
                    installation_id=10,
                    repository_id=20,
                    owner="karateka-git",
                    repository="my_obs_data",
                    branch="main",
                ),
            )
        )

        self.assertIn("Регистрация завершена", reply)
        self.assertIn("karateka-git/my_obs_data", reply)

    def test_format_incoming_message_result_reports_link_code(self) -> None:
        """Код привязки форматируется как команда для второго канала."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_CODE_CREATED,
                link_code=CreatedLinkCode(
                    code="ABC123",
                    expires_at=datetime(2026, 7, 17, tzinfo=UTC),
                ),
            )
        )

        self.assertIn("ABC123", reply)
        self.assertIn("/link ABC123", reply)

    def test_format_incoming_message_result_reports_rebind_confirmation(self) -> None:
        """Запрос перепривязки просит ответить да или нет."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_REBIND_CONFIRMATION_REQUIRED,
                app_user=AppUser(id=99, display_name="Основной профиль"),
            )
        )

        self.assertIn("Перепривязать", reply)
        self.assertIn("Основной профиль", reply)
        self.assertNotIn("99", reply)
        self.assertIn("да", reply)
        self.assertIn("нет", reply)

    def test_format_incoming_message_result_reports_rebind_success(self) -> None:
        """Подтвержденная перепривязка сообщает нового пользователя."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_REBOUND,
                app_user=AppUser(id=99, display_name="Основной профиль"),
            )
        )

        self.assertIn("перепривязал", reply)
        self.assertIn("Основной профиль", reply)
        self.assertNotIn("99", reply)

    def test_format_incoming_message_result_reports_pending_rebind(self) -> None:
        """Pending-перепривязка просит ответить да или нет."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_REBIND_CONFIRMATION_PENDING,
            )
        )

        self.assertIn("жду ответ", reply)
        self.assertIn("да", reply)
        self.assertIn("нет", reply)

    def test_format_incoming_message_result_reports_processing_error(self) -> None:
        """Ошибка article pipeline получает понятный текст ответа."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_PROCESSING_FAILED,
                error=ProcessArticleUrlError(
                    "Could not fetch article HTML: failed",
                    stage=ProcessingStage.FETCHING,
                ),
            )
        )

        self.assertIn("Не удалось загрузить страницу", reply)

    def test_format_incoming_message_result_reports_status(self) -> None:
        """Команда статуса сообщает имя и состояние vault без внутреннего ID."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.STATUS,
                app_user=AppUser(id=42, display_name="Влад"),
            )
        )

        self.assertIn("Бот работает", reply)
        self.assertIn("Влад", reply)
        self.assertIn("ещё не подключён", reply)
        self.assertNotIn("42", reply)

    def test_format_github_authorization_returns_device_url_and_code(self) -> None:
        """Оба channel adapters получают безопасную инструкцию Device Flow."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_CONNECT_STARTED,
                app_user=AppUser(id=42),
                github_connection=GitHubConnectionStartResult(
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
                ),
            )
        )

        self.assertNotIn("installations/new", reply)
        self.assertIn("https://github.com/login/device", reply)
        self.assertIn("ABCD-EFGH", reply)
        self.assertNotIn("device-secret", reply)

    def test_format_github_failure_covers_final_error_statuses(self) -> None:
        """Ошибки Device Flow предлагают повторить отправку repository URL."""
        cases = {
            GitHubConnectionCompletionStatus.DENIED: "отклонена",
            GitHubConnectionCompletionStatus.EXPIRED: "истёк",
            GitHubConnectionCompletionStatus.FAILED: "Не удалось",
        }

        for status, expected_text in cases.items():
            with self.subTest(status=status):
                reply = format_incoming_message_result(
                    ProcessIncomingMessageResult(
                        type=IncomingMessageResultType.GITHUB_CONNECT_FAILED,
                        github_completion=GitHubConnectionCompletion(status),
                    )
                )
                self.assertIn(expected_text, reply)
                self.assertIn("ссылку", reply)

    def test_format_github_app_required_returns_installation_url(self) -> None:
        """После OAuth без installation бот предлагает настроить App."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_APP_REQUIRED,
                installation_url=(
                    "https://github.com/apps/obs-chat-bot/installations/new"
                ),
            )
        )

        self.assertIn("installations/new", reply)
        self.assertIn("read and write", reply)

    def test_format_vault_selection_shows_repository_branch_and_path(self) -> None:
        """Успешный выбор vault возвращает понятные проверенные параметры."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_SELECTED,
                app_user=AppUser(id=42),
                vault_selection=VaultSelectionResult(
                    VaultSelectionStatus.SELECTED,
                    ObsidianVault(
                        id=1,
                        app_user_id=42,
                        installation_id=101,
                        repository_id=501,
                        owner="octocat",
                        repository="notes",
                        branch="main",
                        root_path="Vault",
                    ),
                ),
            )
        )

        self.assertIn("Obsidian vault подключён", reply)
        self.assertIn("octocat/notes", reply)
        self.assertIn("main", reply)
        self.assertIn("Vault", reply)

    def test_format_unavailable_vault_explains_required_write_access(self) -> None:
        """Ошибка выбора объясняет требование чтения и записи repository."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.GITHUB_VAULT_REPOSITORY_UNAVAILABLE,
            )
        )

        self.assertIn("чтение и запись", reply)
        self.assertIn("Contents: read and write", reply)

    def test_format_vault_replacement_requests_yes_or_no(self) -> None:
        """Предложение замены явно предупреждает об удалении локальных данных."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=(
                    IncomingMessageResultType
                    .GITHUB_VAULT_REPLACEMENT_CONFIRMATION_REQUIRED
                ),
                vault_selection=VaultSelectionResult(
                    VaultSelectionStatus.REPLACEMENT_CONFIRMATION_REQUIRED,
                    ObsidianVault(
                        app_user_id=42,
                        installation_id=101,
                        repository_id=502,
                        owner="octocat",
                        repository="second",
                        branch="main",
                    ),
                ),
            )
        )

        self.assertIn("заменит текущее", reply)
        self.assertIn("да", reply)
        self.assertIn("нет", reply)

    def test_format_vault_disconnect_explains_scope_and_confirmation(self) -> None:
        """Отключение предупреждает об очистке локальных, но не пользовательских данных."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=(
                    IncomingMessageResultType
                    .GITHUB_DISCONNECT_CONFIRMATION_REQUIRED
                ),
                vault_disconnect=VaultDisconnectResult(
                    VaultDisconnectStatus.CONFIRMATION_REQUIRED,
                    ObsidianVault(
                        id=1,
                        app_user_id=42,
                        installation_id=101,
                        repository_id=501,
                        owner="octocat",
                        repository="notes",
                        branch="main",
                    ),
                ),
            )
        )

        self.assertIn("octocat/notes", reply)
        self.assertIn("GitHub repository не изменится", reply)
        self.assertIn("статьи и анализы сохранятся", reply)
        self.assertIn("да", reply)
        self.assertIn("нет", reply)

    def test_format_sync_failure_keeps_article_result_and_warns_about_fallback(
        self,
    ) -> None:
        """Сбой GitHub сохраняет основной ответ и поясняет локальный fallback."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_PROCESSED,
                article_result=ProcessArticleUrlResult(
                    article=_article(),
                    created=True,
                    extracted=True,
                ),
                vault_sync_warning=VaultSyncWarning(
                    reason=VaultSyncWarningReason.UPDATE_FAILED,
                    note_count=17,
                    last_checked_at=datetime(
                        2026,
                        7,
                        30,
                        7,
                        15,
                        tzinfo=UTC,
                    ),
                ),
            )
        )

        self.assertIn("статья сохранена.", reply)
        self.assertIn("последняя локальная копия", reply)
        self.assertIn("Локально заметок: 17.", reply)
        self.assertIn("2026-07-30 07:15 UTC", reply)

    def test_format_sync_in_progress_warns_about_current_local_copy(self) -> None:
        """Параллельная синхронизация не скрывает успешный результат статьи."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_PROCESSED,
                article_result=ProcessArticleUrlResult(
                    article=_article(),
                    created=True,
                    extracted=True,
                ),
                vault_sync_warning=VaultSyncWarning(
                    reason=VaultSyncWarningReason.IN_PROGRESS,
                    note_count=17,
                ),
            )
        )

        self.assertIn("статья сохранена.", reply)
        self.assertIn("другом связанном канале", reply)
        self.assertIn("текущая локальная копия", reply)

    def test_format_incoming_message_result_reports_reanalysis(self) -> None:
        """Повторный анализ форматируется как полезный Markdown-ответ."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.ARTICLE_REANALYZED,
                analysis_result=AnalyzeArticleResult(
                    article=replace(_article(), status=ArticleStatus.ANALYZED),
                    analysis=ArticleAnalysisResult(
                        id=2,
                        article_id=1,
                        llm_model="fake-llm",
                        prompt_version="article-summary-v1",
                        result_text="## Кратко\nОбновлено.",
                    ),
                    created=True,
                ),
            )
        )

        self.assertIn("Анализ обновлен.", reply)
        self.assertIn("## Кратко", reply)


def _article() -> Article:
    """Создает минимальную статью для тестов пользовательских ответов."""
    return Article(
        id=1,
        source_url="https://example.com/article",
        normalized_url="https://example.com/article",
        title="Article title",
        cleaned_text="Clean text.",
        status=ArticleStatus.EXTRACTED,
    )


if __name__ == "__main__":
    unittest.main()
