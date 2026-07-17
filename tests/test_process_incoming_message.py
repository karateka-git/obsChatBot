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
from obs_chat_bot.application.incoming.processing import (
    IncomingMessageResultType,
    ProcessIncomingMessageUseCase,
)
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus


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


if __name__ == "__main__":
    unittest.main()
