"""Тесты CLI-команды обработки URL статьи."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from obs_chat_bot.application.articles.processing import (
    ProcessArticleUrlCommand,
    ProcessArticleUrlError,
    ProcessArticleUrlResult,
)
from obs_chat_bot.domain.articles.entities import Article
from obs_chat_bot.domain.articles.statuses import ArticleStatus
from obs_chat_bot.presentation.cli.main import parse_args, run_process_url_command
from obs_chat_bot.presentation.cli.main import run_telegram_bot_command
from obs_chat_bot.presentation.telegram.bot import TelegramBotError


class SilentLogger:
    """Logger-заглушка для CLI-тестов без вывода в консоль."""

    def info(self, *_args: object, **_kwargs: object) -> None:
        """Игнорирует info-сообщение."""

    def error(self, *_args: object, **_kwargs: object) -> None:
        """Игнорирует error-сообщение."""


class FakeProcessArticleUrlUseCase:
    """Fake use case для проверки CLI без сети и extractor."""

    def __init__(self, *, error: ProcessArticleUrlError | None = None) -> None:
        self.commands: list[ProcessArticleUrlCommand] = []
        self._error = error

    def execute(self, command: ProcessArticleUrlCommand) -> ProcessArticleUrlResult:
        """Возвращает успешный результат или выбрасывает заданную ошибку."""
        self.commands.append(command)
        if self._error is not None:
            raise self._error

        return ProcessArticleUrlResult(
            article=Article(
                id=1,
                source_url=command.source_url,
                normalized_url="https://example.com/article",
                title="Article title",
                cleaned_text="Clean text",
                text_hash="hash",
                status=ArticleStatus.EXTRACTED,
            ),
            created=True,
            extracted=True,
        )


class ProcessUrlCliTest(unittest.TestCase):
    """Проверяет CLI-команду `--process-url`."""

    def test_parse_args_reads_process_url(self) -> None:
        """CLI принимает URL как отдельный режим запуска."""
        with patch(
            "sys.argv",
            ["obs-chat-bot", "--process-url", "https://example.com/article"],
        ):
            args = parse_args()

        self.assertEqual(args.process_url, "https://example.com/article")
        self.assertFalse(args.healthcheck)
        self.assertFalse(args.sqlite_smoke)

    def test_parse_args_reads_pipeline_smoke(self) -> None:
        """CLI принимает pipeline smoke как отдельный режим запуска."""
        with patch("sys.argv", ["obs-chat-bot", "--pipeline-smoke"]):
            args = parse_args()

        self.assertTrue(args.pipeline_smoke)
        self.assertFalse(args.healthcheck)
        self.assertFalse(args.sqlite_smoke)
        self.assertIsNone(args.process_url)

    def test_parse_args_reads_analysis_smoke(self) -> None:
        """CLI принимает analysis smoke как отдельный режим запуска."""
        with patch("sys.argv", ["obs-chat-bot", "--analysis-smoke"]):
            args = parse_args()

        self.assertTrue(args.analysis_smoke)
        self.assertFalse(args.healthcheck)
        self.assertFalse(args.sqlite_smoke)
        self.assertIsNone(args.process_url)

    def test_parse_args_reads_telegram_bot(self) -> None:
        """CLI принимает запуск Telegram-бота как отдельный режим."""
        with patch("sys.argv", ["obs-chat-bot", "--telegram-bot"]):
            args = parse_args()

        self.assertTrue(args.telegram_bot)
        self.assertFalse(args.healthcheck)
        self.assertFalse(args.sqlite_smoke)
        self.assertIsNone(args.process_url)

    def test_run_process_url_command_returns_zero_on_success(self) -> None:
        """Успешный pipeline возвращает нулевой exit code."""
        fake_use_case = FakeProcessArticleUrlUseCase()

        with TemporaryDirectory(prefix="obs-chat-bot-cli-") as temporary_directory:
            exit_code = run_process_url_command(
                database_path=Path(temporary_directory) / "test.db",
                source_url="https://example.com/article",
                logger=SilentLogger(),
                use_case_factory=lambda _connection: fake_use_case,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_use_case.commands[0].source_url, "https://example.com/article")

    def test_run_process_url_command_returns_one_on_pipeline_error(self) -> None:
        """Ошибка use case превращается в ненулевой exit code."""
        fake_use_case = FakeProcessArticleUrlUseCase(
            error=ProcessArticleUrlError("failed")
        )

        with TemporaryDirectory(prefix="obs-chat-bot-cli-") as temporary_directory:
            exit_code = run_process_url_command(
                database_path=Path(temporary_directory) / "test.db",
                source_url="https://example.com/article",
                logger=SilentLogger(),
                use_case_factory=lambda _connection: fake_use_case,
            )

        self.assertEqual(exit_code, 1)

    def test_run_telegram_bot_command_returns_zero_on_stop(self) -> None:
        """Штатное завершение Telegram adapter возвращает нулевой exit code."""
        fake_use_case = FakeProcessArticleUrlUseCase()
        with patch("obs_chat_bot.presentation.cli.main.run_telegram_bot") as runner:
            with TemporaryDirectory(prefix="obs-chat-bot-telegram-") as temporary_directory:
                exit_code = run_telegram_bot_command(
                    database_path=Path(temporary_directory) / "test.db",
                    token="token",
                    logger=SilentLogger(),
                    use_case_factory=lambda _connection: fake_use_case,
                )

        runner.assert_called_once()
        self.assertEqual(exit_code, 0)

    def test_run_telegram_bot_command_returns_one_on_adapter_error(self) -> None:
        """Ошибка Telegram adapter превращается в ненулевой exit code."""
        fake_use_case = FakeProcessArticleUrlUseCase()
        with patch(
            "obs_chat_bot.presentation.cli.main.run_telegram_bot",
            side_effect=TelegramBotError("failed"),
        ):
            with TemporaryDirectory(prefix="obs-chat-bot-telegram-") as temporary_directory:
                exit_code = run_telegram_bot_command(
                    database_path=Path(temporary_directory) / "test.db",
                    token="token",
                    logger=SilentLogger(),
                    use_case_factory=lambda _connection: fake_use_case,
                )

        self.assertEqual(exit_code, 1)

    def test_run_telegram_bot_command_passes_use_case(self) -> None:
        """Telegram adapter получает собранный use case."""
        fake_use_case = FakeProcessArticleUrlUseCase()
        fake_analysis_use_case = object()
        with patch("obs_chat_bot.presentation.cli.main.run_telegram_bot") as runner:
            with TemporaryDirectory(prefix="obs-chat-bot-telegram-") as temporary_directory:
                exit_code = run_telegram_bot_command(
                    database_path=Path(temporary_directory) / "test.db",
                    token="token",
                    logger=SilentLogger(),
                    use_case_factory=lambda _connection: fake_use_case,
                    analysis_use_case_factory=lambda _connection: fake_analysis_use_case,
                )

        incoming_use_case = runner.call_args.kwargs["incoming_message_use_case"]
        self.assertIs(incoming_use_case._article_url_use_case, fake_use_case)
        self.assertIs(
            incoming_use_case._article_analysis_use_case,
            fake_analysis_use_case,
        )
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
