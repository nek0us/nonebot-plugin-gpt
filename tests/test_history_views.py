import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
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

    def test_persona_prompt_is_hidden_and_visible_indexes_are_remapped(self):
        history = [
            {"Q": "你是一位冷静的船长", "A": "已就位"},
            {"Q": "下一站去哪里？", "A": "去港口"},
            {"Q": "带上地图", "A": "已经收好"},
        ]

        projection = history_views.project_history(history, persona_prompt="你是一位冷静的船长")

        self.assertEqual(len(projection.entries), 2)
        self.assertEqual(projection.resolve_rewind_reference("1"), "2")
        self.assertEqual(projection.resolve_rewind_reference("2"), "3")
        self.assertEqual(projection.resolve_rewind_reference("-1"), "-1")

    def test_reinforced_persona_prompt_is_hidden_outside_first_round(self):
        history = [
            {"Q": "第一句普通对话", "A": "第一答"},
            {"Q": "请遵守：你是一位冷静的船长\n继续聊天", "A": "收到"},
            {"Q": "继续航行", "A": "出发"},
        ]

        projection = history_views.project_history(history, persona_prompt="你是一位冷静的船长")

        self.assertEqual(
            [item["Q"] for item in projection.entries],
            ["第一句普通对话", "继续航行"],
        )
        self.assertEqual(projection.resolve_rewind_reference("2"), "3")

    def test_legacy_persona_session_hides_the_first_round_without_prompt_snapshot(self):
        projection = history_views.project_history(
            [{"Q": "私有人设正文", "A": "已就位"}, {"Q": "你好", "A": "你好"}],
            hide_initial=True,
        )

        self.assertEqual([item["Q"] for item in projection.entries], ["你好"])
        self.assertEqual(projection.resolve_rewind_reference("1"), "2")

    def test_history_shows_group_speaker_name_by_default(self):
        history = [
            {
                "Q": '[群聊发言者] {"id": "onebot.v11:user:42", "name": "小明"}\n你好',
                "A": "你好，小明。",
            }
        ]

        text = history_views.format_history(history)

        self.assertIn("用户 · 小明：你好", text)
        self.assertNotIn("群聊发言者", text)

    def test_history_reverse_order_keeps_the_original_round_numbers(self):
        history = [
            {"Q": "第一问", "A": "第一答"},
            {"Q": "第二问", "A": "第二答"},
            {"Q": "第三问", "A": "第三答"},
        ]

        value, reverse_order = history_views.parse_history_view_argument("2-3 倒序")
        text = history_views.format_history(history, value, reverse_order=reverse_order)

        self.assertLess(text.index("3. 用户：第三问"), text.index("2. 用户：第二问"))
        self.assertNotIn("1. 用户：第一问", text)

    def test_history_can_anonymize_group_speaker(self):
        history = [
            {
                "Q": '[群聊发言者] {"id": "onebot.v11:user:42", "name": "小明"}\n你好',
                "A": "你好，小明。",
            }
        ]

        text = history_views.format_history(history, anonymize=True)

        self.assertIn("用户：你好", text)
        self.assertNotIn("用户 · 小明", text)
