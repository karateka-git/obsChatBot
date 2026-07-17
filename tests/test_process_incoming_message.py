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
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.analysis import ArticleAnalysisResult
from obs_chat_bot.domain.articles.statuses import ArticleStatus
from obs_chat_bot.application.users.identity import IdentityAlreadyBoundError
from obs_chat_bot.domain.users.entities import AppUser, IncomingIdentity


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
        self.app_user = AppUser(id=42)

    def resolve(self, _identity: IncomingIdentity) -> AppUser | None:
        """Всегда возвращает пользователя."""
        return self.app_user

    def confirm_rebind(self, _identity: IncomingIdentity) -> AppUser:
        """Возвращает пользователя для тестов подтверждения перепривязки."""
        return self.app_user

    def cancel_rebind(self, _identity: IncomingIdentity) -> None:
        """Запоминает отмену перепривязки."""


class FakeRebindIdentityService(FakeUserIdentityService):
    """Fake identity service для проверки подтверждения перепривязки."""

    def __init__(self) -> None:
        super().__init__()
        self.target_user = AppUser(id=99)
        self.rebind_requested = False
        self.rebind_confirmed = False
        self.rebind_cancelled = False

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
        return self.target_user

    def confirm_rebind(self, _identity: IncomingIdentity) -> AppUser:
        """Имитирует подтвержденную перепривязку."""
        self.rebind_confirmed = True
        return self.target_user

    def cancel_rebind(self, _identity: IncomingIdentity) -> None:
        """Имитирует отмену перепривязки."""
        self.rebind_cancelled = True


class FakeRegisteringIdentityService:
    """Fake identity service для проверки регистрации и `/start`."""

    def __init__(self, existing: AppUser | None = None) -> None:
        self.app_user = existing or AppUser(id=77)
        self.register_calls = 0
        self._existing = existing

    def resolve(self, _identity: IncomingIdentity) -> AppUser | None:
        """Возвращает существующего пользователя, если он задан."""
        return self._existing

    def register(self, _identity: IncomingIdentity) -> AppUser:
        """Создает пользователя и запоминает регистрацию."""
        self.register_calls += 1
        self._existing = self.app_user
        return self.app_user


class ProcessIncomingMessageUseCaseTest(unittest.TestCase):
    """Проверяет общий application-flow без Telegram adapter."""

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

    def test_execute_registers_new_identity(self) -> None:
        """Команда `/register` создает пользователя для нового канала."""
        identity_service = FakeRegisteringIdentityService()
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("/register"))

        self.assertEqual(result.type, IncomingMessageResultType.REGISTERED)
        self.assertEqual(result.app_user.id, 77)
        self.assertEqual(identity_service.register_calls, 1)

    def test_execute_reports_already_registered_identity(self) -> None:
        """Повторный `/register` не создает пользователя заново."""
        identity_service = FakeRegisteringIdentityService(existing=AppUser(id=42))
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
        identity_service = FakeRegisteringIdentityService(existing=AppUser(id=42))
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
        use_case = ProcessIncomingMessageUseCase(
            article_url_use_case=FakeArticleUrlUseCase(),
            user_identity_service=identity_service,
        )

        result = use_case.execute(_telegram_message("нет"))

        self.assertEqual(result.type, IncomingMessageResultType.LINK_REBIND_CANCELLED)
        self.assertTrue(identity_service.rebind_cancelled)

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


if __name__ == "__main__":
    unittest.main()
