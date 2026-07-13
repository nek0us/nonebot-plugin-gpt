import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
conversation = importlib.import_module("nonebot_plugin_gpt.conversation")
session_commands = importlib.import_module("nonebot_plugin_gpt.session_commands")


class SessionCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_list_hides_physical_conversation_ids(self):
        state = conversation.ConversationState(
            conversation_id="physical-id-must-not-appear",
            label="港口剧情",
            persona_name="船长",
            model="gpt-5",
        )
        state.logical_id = "logical-id"

        text = session_commands.format_sessions([state], state.logical_id)

        self.assertIn("港口剧情", text)
        self.assertIn("船长", text)
        self.assertNotIn("physical-id-must-not-appear", text)

    async def test_switch_uses_visible_position_not_a_physical_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = conversation.ConversationStore(Path(directory) / "sessions.json")
            key = conversation.ConversationKey("satori:channel:7", "alice")
            first = await store.create(key, "第一段")
            second = await store.create(key, "第二段")
            first.updated_at = "2026-01-01T00:00:00+00:00"
            second.updated_at = "2026-01-02T00:00:00+00:00"
            await store.save(key, first)
            await store.save(key, second)

            class Runtime:
                _conversations = store

                async def list_sessions(self, current_key):
                    return await store.list(current_key)

                async def switch_session(self, current_key, logical_id):
                    return await store.switch(current_key, logical_id)

            text = await session_commands.switch_session(Runtime(), key, "2")

            self.assertIn("第一段", text)
            self.assertEqual((await store.get(key)).logical_id, first.logical_id)
            self.assertNotEqual((await store.get(key)).logical_id, second.logical_id)
