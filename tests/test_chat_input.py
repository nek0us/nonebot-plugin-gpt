import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
chat_input = importlib.import_module("nonebot_plugin_gpt.chat_input")


class ChatInputTests(unittest.TestCase):
    def test_nickname_preserves_the_original_natural_subject_by_default(self):
        prompt = chat_input.build_chat_prompt(
            "今天吃什么",
            original_text="猪咪今天吃什么",
            nicknames=["猪咪"],
            chat_prefixes=[],
            include_prefix=False,
            empty_trigger_prompt="有人在呼唤你。",
        )

        self.assertEqual(prompt, "猪咪今天吃什么")

    def test_nickname_only_or_repeated_nickname_uses_the_persona_friendly_prompt(self):
        prompt = chat_input.build_chat_prompt(
            "",
            original_text="猪咪猪咪",
            nicknames=["猪咪"],
            chat_prefixes=[],
            include_prefix=False,
            empty_trigger_prompt="有人在呼唤你。",
        )

        self.assertEqual(prompt, "有人在呼唤你。")

    def test_direct_address_context_is_opt_in_and_keeps_original_text(self):
        prompt = chat_input.build_chat_prompt(
            "今天吃什么",
            original_text="猪咪今天吃什么",
            nicknames=["猪咪"],
            chat_prefixes=[],
            include_prefix=False,
            empty_trigger_prompt="有人在呼唤你。",
            direct_address_context_enabled=True,
            direct_address_context_prompt="请自然理解称呼。",
        )

        self.assertIn("请自然理解称呼。", prompt)
        self.assertIn("用户消息：猪咪今天吃什么", prompt)

    def test_at_only_message_uses_the_empty_trigger_prompt(self):
        self.assertEqual(
            chat_input.build_chat_prompt(
                "",
                original_text="",
                nicknames=["猪咪"],
                chat_prefixes=["猪咪"],
                include_prefix=False,
                empty_trigger_prompt="有人在呼唤你。",
            ),
            "有人在呼唤你。",
        )

    def test_include_prefix_keeps_the_original_message(self):
        self.assertEqual(
            chat_input.build_chat_prompt(
                "猪咪今天吃什么",
                original_text="猪咪今天吃什么",
                nicknames=[],
                chat_prefixes=["猪咪"],
                include_prefix=True,
                empty_trigger_prompt="有人在呼唤你。",
            ),
            "猪咪今天吃什么",
        )
