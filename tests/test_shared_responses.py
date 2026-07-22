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
from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionCompletion,
    GitHubConnectionCompletionStatus,
    GitHubConnectionStartResult,
    GitHubConnectionStartStatus,
    GitHubDeviceAuthorization,
)
from obs_chat_bot.application.users.identity import CreatedLinkCode
from obs_chat_bot.domain.articles.analysis import ArticleAnalysisResult
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus
from obs_chat_bot.domain.users.entities import AppUser
from obs_chat_bot.presentation.shared.responses import (
    format_article_analysis_result,
    format_article_processing_result,
    format_github_connection_completion,
    format_incoming_message_result,
)


class TelegramResponsesTest(unittest.TestCase):
    """Проверяет пользовательский текст по результату обработки статьи."""

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
        """`/start` для зарегистрированного канала показывает user id."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.START_REGISTERED,
                app_user=AppUser(id=42),
            )
        )

        self.assertIn("уже привязан", reply)
        self.assertIn("ID 42", reply)

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
                app_user=AppUser(id=42),
            )
        )

        self.assertIn("уже зарегистрирован", reply)
        self.assertIn("ID пользователя: 42", reply)

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
                app_user=AppUser(id=99),
            )
        )

        self.assertIn("Перепривязать", reply)
        self.assertIn("ID 99", reply)
        self.assertIn("да", reply)
        self.assertIn("нет", reply)

    def test_format_incoming_message_result_reports_rebind_success(self) -> None:
        """Подтвержденная перепривязка сообщает нового пользователя."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.LINK_REBOUND,
                app_user=AppUser(id=99),
            )
        )

        self.assertIn("перепривязал", reply)
        self.assertIn("ID 99", reply)

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
        """Команда статуса сообщает ID пользователя и доступные действия."""
        reply = format_incoming_message_result(
            ProcessIncomingMessageResult(
                type=IncomingMessageResultType.STATUS,
                app_user=AppUser(id=42),
            )
        )

        self.assertIn("Бот работает", reply)
        self.assertIn("ID пользователя: 42", reply)

    def test_format_github_connect_returns_install_url_device_url_and_code(self) -> None:
        """Оба channel adapters получают полную безопасную инструкцию Device Flow."""
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

        self.assertIn("installations/new", reply)
        self.assertIn("https://github.com/login/device", reply)
        self.assertIn("ABCD-EFGH", reply)
        self.assertNotIn("device-secret", reply)

    def test_format_github_completion_covers_all_final_statuses(self) -> None:
        """Каждый финал Device Flow получает понятный безопасный ответ."""
        cases = {
            GitHubConnectionCompletionStatus.CONNECTED: "успешно подключён",
            GitHubConnectionCompletionStatus.NO_INSTALLATIONS: "не найдено",
            GitHubConnectionCompletionStatus.DENIED: "отклонена",
            GitHubConnectionCompletionStatus.EXPIRED: "истёк",
            GitHubConnectionCompletionStatus.FAILED: "Не удалось",
        }

        for status, expected_text in cases.items():
            with self.subTest(status=status):
                count = 1 if status is GitHubConnectionCompletionStatus.CONNECTED else 0
                reply = format_github_connection_completion(
                    GitHubConnectionCompletion(status, installation_count=count)
                )
                self.assertIn(expected_text, reply)

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
    format_github_connection_completion,
