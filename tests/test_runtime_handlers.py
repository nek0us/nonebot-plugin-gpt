import importlib
import sys
import types
import unittest
from pathlib import Path

from ChatGPTWeb import ChatContent, ChatResult


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
conversation = importlib.import_module("nonebot_plugin_gpt.conversation")
runtime_handlers = importlib.import_module("nonebot_plugin_gpt.runtime_handlers")


class RuntimeHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_reply_uses_runtime_and_returns_plain_cross_platform_message(self):
        class Runtime:
            async def chat(self, key, prompt, **kwargs):
                self.key = key
                self.prompt = prompt
                self.kwargs = kwargs
                return ChatResult(
                    ok=True,
                    text="你好",
                    conversation_id="conversation",
                    message_id="message",
                    content=ChatContent(markdown="你好", plain_text="你好"),
                )

        runtime = Runtime()
        key = conversation.ConversationKey("telegram:private:1", "alice")

        message = await runtime_handlers.chat_reply(
            runtime,
            key,
            "你好",
            model="gpt-5",
            render_markdown=None,
        )

        self.assertEqual(runtime.key, key)
        self.assertEqual(runtime.prompt, "你好")
        self.assertEqual(runtime.kwargs["model"], "gpt-5")
        self.assertTrue(runtime.kwargs["web_search"])
        self.assertEqual(message.extract_plain_text(), "你好")

    async def test_persona_reply_returns_a_clear_message_when_persona_is_missing(self):
        class Runtime:
            async def initialize_persona(self, *args, **kwargs):
                raise ValueError("未找到指定人设")

        message = await runtime_handlers.persona_reply(
            Runtime(),
            conversation.ConversationKey("satori:channel:7", "alice"),
            "不存在",
            render_markdown=None,
        )

        self.assertEqual(message.extract_plain_text(), "未找到指定人设")

    async def test_failed_result_hides_core_error_text(self):
        class Runtime:
            async def chat(self, *args, **kwargs):
                return ChatResult(
                    ok=False,
                    text="send msg retry max: token=internal-secret",
                    conversation_id="",
                    message_id="",
                    errors=[{"kind": "send_retry_max", "message": "internal-secret"}],
                )

        message = await runtime_handlers.chat_reply(
            Runtime(),
            conversation.ConversationKey("telegram:private:1", "alice"),
            "你好",
            render_markdown=None,
        )

        text = message.extract_plain_text()
        self.assertIn("没能顺利回应", text)
        self.assertNotIn("internal-secret", text)
        self.assertNotIn("retry max", text)
        self.assertNotIn("账号", text)
        self.assertNotIn("模型", text)

    async def test_custom_error_message_is_used_for_failed_result(self):
        class Runtime:
            async def chat(self, *args, **kwargs):
                return ChatResult(
                    ok=False,
                    text="internal error",
                    conversation_id="",
                    message_id="",
                )

        message = await runtime_handlers.chat_reply(
            Runtime(),
            conversation.ConversationKey("telegram:private:1", "alice"),
            "你好",
            render_markdown=None,
            error_message="系统正在整理思绪，请稍后再来。",
        )

        self.assertEqual(message.extract_plain_text(), "系统正在整理思绪，请稍后再来。")

    async def test_runtime_exception_returns_safe_message(self):
        class Runtime:
            async def chat(self, *args, **kwargs):
                raise RuntimeError("upstream detail should not reach users")

        message = await runtime_handlers.chat_reply(
            Runtime(),
            conversation.ConversationKey("telegram:private:1", "alice"),
            "你好",
            render_markdown=None,
        )

        text = message.extract_plain_text()
        self.assertIn("没能顺利回应", text)
        self.assertNotIn("upstream detail", text)
