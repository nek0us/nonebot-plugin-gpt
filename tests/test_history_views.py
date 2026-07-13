import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
conversation = importlib.import_module("nonebot_plugin_gpt.conversation")
history_views = importlib.import_module("nonebot_plugin_gpt.history_views")


class HistoryViewTests(unittest.TestCase):
    def test_history_range_uses_human_friendly_indexes(self):
        history = [
            {"Q": "第一问", "A": "第一答"},
            {"Q": "第二问", "A": "第二答"},
        ]

        text = history_views.format_history(history, "2")

        self.assertNotIn("第一问", text)
        self.assertIn("第二问", text)

    def test_tree_hides_physical_conversation_ids(self):
        state = conversation.ConversationState(
            conversation_id="physical-id",
            label="港口剧情",
            persona_name="船长",
        )

        text = history_views.format_history_tree(state, 3)

        self.assertIn("港口剧情", text)
        self.assertNotIn("physical-id", text)
