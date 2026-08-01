import importlib
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path

from ChatGPTWeb import ChatResult


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
auto_persona = importlib.import_module("nonebot_plugin_gpt.auto_persona")
conversation = importlib.import_module("nonebot_plugin_gpt.conversation")


@dataclass
class _State:
    conversation_id: str = ""
    persona_name: str = ""


class _Runtime:
    def __init__(self, state: _State | None = None):
        self.state = state or _State()
        self.calls = []

    async def ensure_persona_initialized(self, key, persona_name, **kwargs):
        if self.state.conversation_id or self.state.persona_name:
            return None
        self.calls.append((key, persona_name, kwargs))
        self.state = _State(conversation_id="conversation", persona_name=persona_name)
        return ChatResult(ok=True, text="", conversation_id="conversation", message_id="message")


class AutoPersonaTests(unittest.IsolatedAsyncioTestCase):
    async def test_initializes_group_persona_for_new_logical_session(self):
        runtime = _Runtime()
        initializer = auto_persona.AutoPersonaInitializer(
            runtime,
            group_enabled=True,
            group_persona_name="群聊人设",
        )
        key = conversation.ConversationKey("group:1", "user:1")

        result = await initializer.ensure_initialized(
            key,
            is_shared=True,
            model="auto",
            prefer_paid_account=False,
        )

        self.assertTrue(result and result.ok)
        self.assertEqual(runtime.calls[0][1], "群聊人设")

    async def test_does_not_replace_existing_persona_or_conversation(self):
        runtime = _Runtime(_State(conversation_id="existing", persona_name="手动人设"))
        initializer = auto_persona.AutoPersonaInitializer(
            runtime,
            friend_enabled=True,
            friend_persona_name="私聊人设",
        )

        result = await initializer.ensure_initialized(
            conversation.ConversationKey("private:1", "user:1"),
            is_shared=False,
            model="auto",
            prefer_paid_account=False,
        )

        self.assertIsNone(result)
        self.assertEqual(runtime.calls, [])

    async def test_missing_configured_persona_leaves_first_message_unpersonaed(self):
        class MissingPersonaRuntime(_Runtime):
            async def ensure_persona_initialized(self, *args, **kwargs):
                raise ValueError("未找到指定人设")

        runtime = MissingPersonaRuntime()
        initializer = auto_persona.AutoPersonaInitializer(
            runtime,
            group_enabled=True,
            group_persona_name="已删除的人设",
        )

        result = await initializer.ensure_initialized(
            conversation.ConversationKey("group:1", "user:1"),
            is_shared=True,
            model="auto",
            prefer_paid_account=False,
        )

        self.assertIsNone(result)
