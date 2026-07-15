import tempfile
import unittest
import sys
import types
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)

from nonebot_plugin_gpt import conversation

ConversationKey = conversation.ConversationKey
ConversationState = conversation.ConversationState
ConversationStore = conversation.ConversationStore


class ConversationStoreTests(unittest.IsolatedAsyncioTestCase):
    def test_group_events_share_one_conversation_key(self):
        def event(sender_id: str):
            value = type("GroupEvent", (), {"__module__": "nonebot.adapters.onebot.v11.event"})()
            value.group_id = "100"
            value.get_session_id = lambda: f"group_100_{sender_id}"
            value.get_user_id = lambda: sender_id
            return value

        first = ConversationKey.from_event(event("alice"))
        second = ConversationKey.from_event(event("bob"))

        self.assertEqual(first.value, "onebot.v11:group:100")
        self.assertEqual(second.value, first.value)

    def test_private_events_keep_users_isolated(self):
        def event(sender_id: str):
            value = type("PrivateEvent", (), {"__module__": "nonebot.adapters.onebot.v11.event"})()
            value.get_session_id = lambda: f"private_{sender_id}"
            value.get_user_id = lambda: sender_id
            return value

        first = ConversationKey.from_event(event("alice"))
        second = ConversationKey.from_event(event("bob"))

        self.assertNotEqual(first.value, second.value)

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

    async def test_logical_sessions_can_be_listed_and_switched(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "sessions.json")
            key = ConversationKey("satori:channel:7", "alice")
            first = await store.create(key, "角色扮演")
            first.conversation_id = "conversation-a"
            await store.save(key, first)
            second = await store.create(key, "普通聊天")
            second.conversation_id = "conversation-b"
            await store.save(key, second)

            sessions = await store.list(key)
            active = await store.switch(key, first.logical_id)

            self.assertEqual({state.label for state in sessions}, {"角色扮演", "普通聊天"})
            self.assertEqual(active.conversation_id, "conversation-a")
            self.assertEqual((await store.get(key)).logical_id, first.logical_id)

    async def test_checkpoint_keeps_the_same_logical_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationStore(Path(directory) / "sessions.json")
            key = ConversationKey("telegram:group:9", "alice")
            state = await store.create(key, "长期角色扮演")
            state = await store.add_checkpoint(
                key,
                state,
                conversation_id="conversation-new",
                parent_message_id="message-new",
                model="gpt-5",
                summary="保留的剧情摘要",
            )

            self.assertEqual(state.conversation_id, "conversation-new")
            self.assertEqual(len(state.checkpoints), 1)
            self.assertEqual((await store.get(key)).logical_id, state.logical_id)
