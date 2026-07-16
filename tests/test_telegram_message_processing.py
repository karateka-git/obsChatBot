"""Тесты обработки Telegram-сообщений без реального Telegram API."""

from dataclasses import replace
import unittest

from obs_chat_bot.application.articles.incoming_messages import (
    IncomingMessage,
    SavedIncomingMessage,
)
from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlError,
    ProcessArticleUrlResult,
)
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus
from obs_chat_bot.presentation.telegram.bot import process_incoming_message


class SilentLogger:
    """Logger-заглушка для тестов Telegram presentation-слоя."""

    def error(self, *_args: object, **_kwargs: object) -> None:
        """Игнорирует error-сообщение."""


class FakeArticleUrlUseCase:
    """Fake use case обработки URL для Telegram-тестов."""

    def __init__(
        self,
        *,
        result: ProcessArticleUrlResult | None = None,
        error: ProcessArticleUrlError | None = None,
    ) -> None:
        self.commands: list[ProcessArticleUrlCommand] = []
        self._result = result or ProcessArticleUrlResult(
            article=Article(
                id=1,
                source_url="https://example.com/article",
                normalized_url="https://example.com/article",
                title="Article title",
                cleaned_text="Clean text",
                status=ArticleStatus.EXTRACTED,
            ),
            created=True,
            extracted=True,
        )
        self._error = error

    def execute(self, command: ProcessArticleUrlCommand) -> ProcessArticleUrlResult:
        """Возвращает заданный результат или ошибку."""
        self.commands.append(command)
        if self._error is not None:
            raise self._error
        return self._result


class FakeIncomingMessageRepository:
    """Fake repository входящих сообщений для Telegram-тестов."""

    def __init__(self) -> None:
        self.messages: list[IncomingMessage] = []
        self.links: list[tuple[int, int]] = []

    def save(self, message: IncomingMessage) -> SavedIncomingMessage:
        """Запоминает сообщение в памяти."""
        self.messages.append(message)
        return SavedIncomingMessage(
            id=len(self.messages),
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
        """Запоминает связь входящего сообщения со статьёй."""
        self.links.append((incoming_message_id, article_id))
        message = self.messages[incoming_message_id - 1]
        return SavedIncomingMessage(
            id=incoming_message_id,
            channel=message.channel,
            chat_id=message.chat_id,
            message_id=message.message_id,
            text=message.text,
            article_id=article_id,
        )


class TelegramMessageProcessingTest(unittest.TestCase):
    """Проверяет presentation-логику Telegram handler."""

    def test_process_incoming_message_asks_for_link_without_url(self) -> None:
        """Сообщение без URL получает просьбу отправить ссылку."""
        use_case = FakeArticleUrlUseCase()
        message_repository = FakeIncomingMessageRepository()

        reply = process_incoming_message(
            IncomingMessage(
                channel="telegram",
                chat_id="1",
                message_id="10",
                text="привет",
            ),
            article_url_use_case=use_case,
            incoming_message_repository=message_repository,
            logger=SilentLogger(),
        )

        self.assertIn("Пришли ссылку", reply)
        self.assertEqual(use_case.commands, [])
        self.assertEqual(message_repository.messages, [])

    def test_process_incoming_message_runs_pipeline_for_url(self) -> None:
        """Сообщение со ссылкой запускает article pipeline."""
        use_case = FakeArticleUrlUseCase()
        message_repository = FakeIncomingMessageRepository()

        reply = process_incoming_message(
            IncomingMessage(
                channel="telegram",
                chat_id="1",
                message_id="10",
                text="https://example.com/article?utm_source=tg",
            ),
            article_url_use_case=use_case,
            incoming_message_repository=message_repository,
            logger=SilentLogger(),
        )

        self.assertIn("Готово: статья сохранена.", reply)
        self.assertIn("Article title", reply)
        self.assertEqual(message_repository.messages[0].message_id, "10")
        self.assertEqual(message_repository.links, [(1, 1)])
        self.assertEqual(
            use_case.commands[0].source_url,
            "https://example.com/article?utm_source=tg",
        )
        self.assertEqual(use_case.commands[0].incoming_message_id, 1)

    def test_process_incoming_message_reports_existing_article(self) -> None:
        """Повторная ссылка получает отдельный текст ответа."""
        result = ProcessArticleUrlResult(
            article=replace(
                FakeArticleUrlUseCase()._result.article,
                title="Existing title",
            ),
            created=False,
            extracted=False,
        )
        use_case = FakeArticleUrlUseCase(result=result)

        reply = process_incoming_message(
            IncomingMessage(
                channel="telegram",
                chat_id="1",
                message_id="10",
                text="https://example.com/article",
            ),
            article_url_use_case=use_case,
            logger=SilentLogger(),
        )

        self.assertIn("уже была сохранена", reply)
        self.assertIn("Existing title", reply)

    def test_process_incoming_message_reports_pipeline_error(self) -> None:
        """Ошибка pipeline превращается в понятный ответ пользователю."""
        use_case = FakeArticleUrlUseCase(error=ProcessArticleUrlError("failed"))
        message_repository = FakeIncomingMessageRepository()

        reply = process_incoming_message(
            IncomingMessage(
                channel="telegram",
                chat_id="1",
                message_id="10",
                text="https://example.com/article",
            ),
            article_url_use_case=use_case,
            incoming_message_repository=message_repository,
            logger=SilentLogger(),
        )

        self.assertIn("Не удалось обработать ссылку", reply)
        self.assertEqual(len(message_repository.messages), 1)
        self.assertEqual(message_repository.links, [])


if __name__ == "__main__":
    unittest.main()
