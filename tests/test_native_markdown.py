import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
native_markdown = importlib.import_module("nonebot_plugin_gpt.native_markdown")


class NativeMarkdownTests(unittest.TestCase):
    def test_only_direct_telegram_adapter_is_marked_as_native_markdown_capable(self):
        class TelegramEvent:
            pass

        TelegramEvent.__module__ = "nonebot.adapters.telegram.event"

        class ConsoleEvent:
            pass

        ConsoleEvent.__module__ = "nonebot.adapters.console.event"

        self.assertTrue(native_markdown.supports_native_markdown(TelegramEvent()))
        self.assertFalse(native_markdown.supports_native_markdown(ConsoleEvent()))

    def test_markdown_is_projected_to_styled_text_and_clickable_url(self):
        message = native_markdown.markdown_to_unimessage(
            "# 标题\n\n**重点** [百科](https://example.com)\n\n- 第一项"
        )
        text = message.extract_plain_text()
        styles = [style for segment in message for style in segment.styles.values()]

        self.assertIn("标题", text)
        self.assertIn("重点", text)
        self.assertIn("百科 (https://example.com)", text)
        self.assertIn("• 第一项", text)
        self.assertTrue(any("bold" in style for style in styles))
        self.assertTrue(any("link" in style for style in styles))
