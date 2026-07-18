import importlib
import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from ChatGPTWeb import AgentTool, ChatResult
from ChatGPTWeb.config import IOFile


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

    async def get_history(self, _conversation_id):
        return [{"Q": "上一句", "A": "上一答"}]

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


class SequentialService(FakeService):
    def __init__(self):
        super().__init__()
        self.first_request_started = asyncio.Event()
        self.release_first_request = asyncio.Event()

    async def stream_to_callback(self, request, _callback):
        self.requests.append(request)
        sequence = len(self.requests)
        if sequence == 1:
            self.first_request_started.set()
            await self.release_first_request.wait()
        return ChatResult(
            ok=True,
            text=f"reply-{sequence}",
            conversation_id="shared-conversation",
            message_id=f"message-{sequence}",
            used_model="gpt-5",
        )


class ChatRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_uses_an_isolated_control_conversation(self):
        class AgentService(FakeService):
            async def send(self, request):
                self.requests.append(request)
                return ChatResult(
                    ok=True,
                    text='{"type":"final","answer":"提醒已安排。"}',
                    conversation_id="agent-control",
                    message_id="agent-message",
                    used_model="gpt-5",
                )

        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = AgentService()
            runtime = chat_runtime.ChatRuntime(service, store, context_policy.ContextPolicy(mode="off"))
            key = conversation.ConversationKey("onebot.v11:group:100", "")
            state = await store.create(key, "角色扮演")
            state.conversation_id = "persona-conversation"
            state.parent_message_id = "persona-message"
            state.model = "gpt-5"
            await store.save(key, state)

            turn = await runtime.agent_turn(
                key,
                "一分钟后提醒我喝水",
                [AgentTool("安排提醒", "安排一次提醒")],
            )
            saved = await store.get(key)

        self.assertTrue(turn.ok)
        self.assertEqual(turn.state.conversation_id, "agent-control")
        self.assertEqual(service.requests[0].conversation_id, "")
        self.assertEqual(service.requests[0].parent_message_id, "")
        self.assertEqual(saved.conversation_id, "persona-conversation")
        self.assertEqual(saved.parent_message_id, "persona-message")

    async def test_shared_conversation_serializes_concurrent_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = SequentialService()
            runtime = chat_runtime.ChatRuntime(
                service,
                store,
                context_policy.ContextPolicy(mode="off"),
            )
            key = conversation.ConversationKey("onebot.v11:group:100", "")

            first = asyncio.create_task(runtime.chat(key, "first"))
            await service.first_request_started.wait()
            second = asyncio.create_task(runtime.chat(key, "second"))
            await asyncio.sleep(0)
            self.assertEqual(len(service.requests), 1)

            service.release_first_request.set()
            await asyncio.gather(first, second)

            self.assertEqual(len(service.requests), 2)
            self.assertEqual(service.requests[1].conversation_id, "shared-conversation")
            self.assertEqual(service.requests[1].parent_message_id, "message-1")

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

    async def test_restart_persona_creates_a_new_logical_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = FakeService()
            runtime = chat_runtime.ChatRuntime(service, store)
            key = conversation.ConversationKey("satori:channel:7", "alice")
            original = await store.create(key, "船长")
            original.persona_name = "船长"
            original.persona_prompt = "你是一位冷静的船长"
            original.conversation_id = "conversation-old"
            await store.save(key, original)

            result = await runtime.restart_persona(key)
            current = await store.get(key)

            self.assertTrue(result.ok)
            self.assertNotEqual(current.logical_id, original.logical_id)
            self.assertEqual(current.persona_name, "船长")

    async def test_rewind_keeps_the_current_logical_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = FakeService()
            runtime = chat_runtime.ChatRuntime(service, store)
            key = conversation.ConversationKey("satori:channel:7", "alice")
            state = await store.create(key, "船长")
            state.conversation_id = "conversation-old"
            state.parent_message_id = "message-old"
            await store.save(key, state)

            result = await runtime.rewind(key, "-1")

            self.assertTrue(result.ok)
            self.assertEqual(service.requests[-1].operation.value, "rewind")
            self.assertEqual(service.requests[-1].reference, "-1")

    async def test_visible_rewind_maps_hidden_persona_rounds(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = FakeService()
            runtime = chat_runtime.ChatRuntime(service, store)
            key = conversation.ConversationKey("satori:channel:7", "alice")
            state = await store.create(key, "船长")
            state.conversation_id = "conversation-old"
            state.parent_message_id = "message-old"
            state.persona_name = "船长"
            state.persona_prompt = "你是一位冷静的船长"
            await store.save(key, state)

            async def get_history(_conversation_id):
                return [
                    {"Q": "你是一位冷静的船长", "A": "已就位"},
                    {"Q": "下一站去哪里？", "A": "去港口"},
                ]

            service.get_history = get_history

            result = await runtime.rewind_visible(key, "1")

            self.assertTrue(result.ok)
            self.assertEqual(service.requests[-1].reference, "2")

    async def test_chat_keeps_uploaded_files_on_the_request(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = FakeService()
            runtime = chat_runtime.ChatRuntime(service, store)
            key = conversation.ConversationKey("satori:channel:7", "alice")
            image = IOFile(content=b"image", name="image.png")

            result = await runtime.chat(key, "看看图片", files=[image])

            self.assertTrue(result.ok)
            self.assertEqual(service.requests[-1].files[0].name, "image.png")

    async def test_history_uses_only_the_active_logical_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            service = FakeService()
            runtime = chat_runtime.ChatRuntime(service, store)
            key = conversation.ConversationKey("satori:channel:7", "alice")
            state = await store.create(key, "船长")
            state.conversation_id = "conversation-active"
            await store.save(key, state)

            history = await runtime.get_history(key)

            self.assertEqual(history, [{"Q": "上一句", "A": "上一答"}])

    async def test_model_preference_is_saved_on_the_logical_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            runtime = chat_runtime.ChatRuntime(FakeService(), store)
            key = conversation.ConversationKey("satori:channel:7", "alice")

            state = await runtime.set_model_preference(
                key,
                "gpt-5",
                prefer_paid_account=True,
            )

            self.assertEqual(state.model, "gpt-5")
            self.assertTrue(state.metadata["prefer_paid_account"])

    async def test_render_mode_is_scoped_separately_from_logical_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            runtime = chat_runtime.ChatRuntime(FakeService(), store)
            first = conversation.ConversationKey("onebot.v11:group:100", "")
            second = conversation.ConversationKey("satori:channel:100", "")

            self.assertEqual(await runtime.get_render_mode(first, "auto"), ("auto", False))
            await runtime.set_render_mode(first, "image")
            await runtime.create_session(first, "新会话")

            self.assertEqual(await runtime.get_render_mode(first, "auto"), ("image", True))
            self.assertEqual(await runtime.get_render_mode(second, "text"), ("text", False))

            await runtime.set_render_mode(first, None)
            self.assertEqual(await runtime.get_render_mode(first, "text"), ("text", False))
