import tempfile
import unittest
import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "conversation.py"
SPEC = importlib.util.spec_from_file_location("conversation", MODULE_PATH)
assert SPEC and SPEC.loader
conversation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = conversation
SPEC.loader.exec_module(conversation)

ConversationKey = conversation.ConversationKey
ConversationState = conversation.ConversationState
ConversationStore = conversation.ConversationStore


class ConversationStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_persists_by_session_and_user(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            store = ConversationStore(path)
            first = ConversationKey("onebot:group:100", "alice")
            second = ConversationKey("telegram:group:100", "alice")

            await store.save(first, ConversationState("conversation-a", "message-a", "gpt-5"))
            await store.save(second, ConversationState("conversation-b", "message-b", "auto"))

            reloaded = ConversationStore(path)
            self.assertEqual((await reloaded.get(first)).conversation_id, "conversation-a")
            self.assertEqual((await reloaded.get(second)).conversation_id, "conversation-b")

    async def test_clear_only_removes_the_requested_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "sessions.json")
            first = ConversationKey("onebot:private:alice", "alice")
            second = ConversationKey("satori:channel:7", "alice")
            await store.save(first, ConversationState("conversation-a", "message-a"))
            await store.save(second, ConversationState("conversation-b", "message-b"))

            await store.clear(first)

            self.assertEqual((await store.get(first)).conversation_id, "")
            self.assertEqual((await store.get(second)).conversation_id, "conversation-b")
