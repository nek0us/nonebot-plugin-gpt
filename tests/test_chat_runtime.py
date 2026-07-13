import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from ChatGPTWeb import ChatResult


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
conversation = importlib.import_module("nonebot_plugin_gpt.conversation")
context_policy = importlib.import_module("nonebot_plugin_gpt.context_policy")
chat_runtime = importlib.import_module("nonebot_plugin_gpt.chat_runtime")


class FakeService:
    def __init__(self):
        self.requests = []

    async def get_persona_prompt(self, name):
        return {"船长": "你是一位冷静的船长"}.get(name, "")

    async def send(self, request):
        self.requests.append(request)
        if "整理一份紧凑状态摘要" in request.prompt:
            return ChatResult(
                ok=True,
                text="船员已抵达港口",
                conversation_id="conversation-old",
                message_id="message-summary",
                used_model="gpt-5",
            )
        return ChatResult(
            ok=True,
            text="人设已初始化",
            conversation_id="conversation-persona",
            message_id="message-persona",
            used_model="gpt-5",
            account="account@example.com",
        )

    async def estimate_context(self, _conversation_id, **_kwargs):
        return SimpleNamespace(estimated_tokens=15_000, context_window_tokens=20_000)

    async def stream_to_callback(self, request, _callback):
        self.requests.append(request)
        return ChatResult(
            ok=True,
            text="新的剧情回复",
            conversation_id="conversation-new",
            message_id="message-new",
            used_model="gpt-5",
            account="account@example.com",
        )


class ChatRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_persona_stores_a_snapshot_for_future_compaction(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = FakeService()
            runtime = chat_runtime.ChatRuntime(service, store, context_policy.ContextPolicy(mode="off"))
            key = conversation.ConversationKey("satori:channel:7", "alice")

            result = await runtime.initialize_persona(key, "船长")
            state = await store.get(key)

            self.assertTrue(result.ok)
            self.assertEqual(service.requests[0].operation.value, "start_persona")
            self.assertEqual(state.persona_name, "船长")
            self.assertEqual(state.persona_prompt, "你是一位冷静的船长")
            self.assertEqual(state.conversation_id, "conversation-persona")

    async def test_compaction_moves_only_the_active_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = FakeService()
            runtime = chat_runtime.ChatRuntime(service, store, context_policy.ContextPolicy())
            key = conversation.ConversationKey("satori:channel:7", "alice")
            state = await store.create(key, "船长剧情")
            state.conversation_id = "conversation-old"
            state.parent_message_id = "message-old"
            state.model = "gpt-5"
            state.persona_name = "船长"
            state.persona_prompt = "你是一位冷静的船长"
            state.metadata["account"] = "account@example.com"
            await store.save(key, state)

            result = await runtime.chat(key, "下一站去哪？")
            updated = await store.get(key)

            self.assertTrue(result.ok)
            self.assertEqual(updated.logical_id, state.logical_id)
            self.assertEqual(updated.conversation_id, "conversation-new")
            self.assertEqual(len(updated.checkpoints), 1)
            self.assertIn("船员已抵达港口", service.requests[-1].prompt)
            self.assertIn("下一站去哪？", service.requests[-1].prompt)
