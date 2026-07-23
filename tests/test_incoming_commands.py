"""Тесты единого реестра пользовательских chat-команд."""

import unittest

from obs_chat_bot.application.incoming.commands import (
    ChatCommand,
    CommandSection,
    ParsedChatCommand,
)


class IncomingCommandsTest(unittest.TestCase):
    """Проверяет metadata команд и точный общий parser."""

    def test_each_command_has_help_metadata_and_markdown_representation(self) -> None:
        """Каждая команда знает раздел, usage и пользовательское описание."""
        for command in ChatCommand:
            with self.subTest(command=command.value):
                self.assertIsInstance(command.section, CommandSection)
                self.assertTrue(command.description)
                self.assertIn(command.value, command.usage)
                self.assertEqual(
                    str(command),
                    f"`{command.usage}` — {command.description}",
                )

    def test_parser_returns_typed_command_and_raw_arguments(self) -> None:
        """Parser отделяет точное имя команды от строки аргументов."""
        parsed = ParsedChatCommand.parse("/link ABC123")

        self.assertEqual(parsed.command, ChatCommand.LINK)
        self.assertEqual(parsed.arguments, "ABC123")

    def test_parser_does_not_confuse_commands_with_common_prefix(self) -> None:
        """`/link_code` не распознаётся как `/link`, а неизвестный prefix отвергается."""
        self.assertEqual(
            ParsedChatCommand.parse("/link_code").command,
            ChatCommand.LINK_CODE,
        )
        self.assertIsNone(ParsedChatCommand.parse("/link_extra ABC123"))
        self.assertIsNone(ParsedChatCommand.parse("/github_connect"))
        self.assertIsNone(
            ParsedChatCommand.parse(
                "/github_vault https://github.com/octocat/notes"
            )
        )
        self.assertIsNone(ParsedChatCommand.parse("обычный текст"))


if __name__ == "__main__":
    unittest.main()
