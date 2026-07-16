import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "command_compat.py"
SPEC = importlib.util.spec_from_file_location("command_compat", MODULE_PATH)
assert SPEC and SPEC.loader
command_compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command_compat)


class LegacyCommandTest(unittest.TestCase):
    def test_alias_keeps_following_argument(self):
        command = command_compat.build_legacy_command("backloop", {"回到过去"})

        result = command.parse("回到过去 3")

        self.assertTrue(result.matched)
        self.assertEqual(command_compat.command_argument_text(result.main_args["argument"]), "3")

    def test_alias_without_argument_is_accepted(self):
        command = command_compat.build_legacy_command("reset", {"重置"})

        result = command.parse("重置")

        self.assertTrue(result.matched)
        self.assertIsNone(result.main_args.get("argument"))

    def test_legacy_chat_help_alias_keeps_the_topic(self):
        command = command_compat.build_legacy_command("gpt_help", {"聊天帮助"})

        result = command.parse("聊天帮助 会话")

        self.assertTrue(result.matched)
        self.assertEqual(command_compat.command_argument_text(result.main_args["argument"]), "会话")

    def test_canonical_command_accepts_an_argument(self):
        command = command_compat.build_legacy_command("添加人设", {"添加人格"})

        result = command.parse("添加人设 旅行助手")

        self.assertTrue(result.matched)
        self.assertEqual(command_compat.command_argument_text(result.main_args["argument"]), "旅行助手")

    def test_command_argument_keeps_the_remaining_words(self):
        command = command_compat.build_legacy_command("智能体", set())

        result = command.parse("智能体 计划 检查当前运行环境")

        self.assertTrue(result.matched)
        self.assertEqual(
            command_compat.command_argument_text(result.main_args["argument"]),
            "计划 检查当前运行环境",
        )

    def test_configured_name_prefix_keeps_the_command_argument(self):
        command = command_compat.build_legacy_command("初始化", {"加载人格"}, ["猪咪"])

        result = command.parse("猪咪 加载人格 猫娘")

        self.assertTrue(result.matched)
        self.assertEqual(command_compat.command_argument_text(result.main_args["argument"]), "猫娘")

    def test_command_and_argument_can_be_written_without_a_space(self):
        command = command_compat.build_legacy_command("输出模式", set(), ["猪咪"])

        for text in ("输出模式文本", "猪咪 输出模式文本", "猪咪输出模式文本"):
            with self.subTest(text=text):
                result = command.parse(text)
                self.assertTrue(result.matched)
                self.assertEqual(
                    command_compat.command_argument_text(result.main_args["argument"]),
                    "文本",
                )
