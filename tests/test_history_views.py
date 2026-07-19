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

    def test_agent_protocol_rounds_are_hidden_and_keep_rewind_mapping(self):
        history = [
            {"Q": "【ChatGPTWeb Agent Protocol】\n工具清单", "A": '{"type":"tool_call"}'},
            {"Q": "你好", "A": "你好呀"},
            {"Q": "【ChatGPTWeb Agent Protocol】\n工具结果", "A": '{"type":"final"}'},
            {"Q": "提醒到时", "A": "记得喝水"},
        ]

        projection = history_views.project_history(history)

        self.assertEqual([item["Q"] for item in projection.entries], ["你好", "提醒到时"])
        self.assertEqual(projection.resolve_rewind_reference("1"), "2")
        self.assertEqual(projection.resolve_rewind_reference("2"), "4")

    def test_agent_presentation_round_shows_original_task_not_control_prompt(self):
        history = [{
            "Q": "【已完成的受控任务】\n下面是可信的任务完成结果。请按当前人设自然回复用户，\n"
                 "不要提及 JSON、协议、工具调用或内部执行过程；不要重复执行任务。\n"
                 "用户原任务：，再画一个你觉得好看的前端登录页面，截图给我看看\n"
                 "完成结果：登录页面设计已完成并生成截图。",
            "A": "页面已经准备好啦咩！",
        }]

        projection = history_views.project_history(history)

        self.assertEqual(projection.entries[0]["Q"], "再画一个你觉得好看的前端登录页面，截图给我看看")
        self.assertEqual(projection.resolve_rewind_reference("1"), "1")
        self.assertNotIn("已完成的受控任务", projection.entries[0]["Q"])

    def test_async_reminder_is_projected_as_an_event_and_keeps_rewind_mapping(self):
        history = [
            {"Q": "你好", "A": "你好呀"},
            {
                "Q": "【异步事件】你之前为当前用户安排的一次提醒现在到时。\n"
                "提醒内容：吃饭",
                "A": "记得吃饭呀。",
            },
        ]

        projection = history_views.project_history(history)

        self.assertEqual(projection.entries[1]["Q"], "提醒到时：吃饭")
        self.assertEqual(projection.entries[1]["_history_speaker"], "提醒事件")
        self.assertEqual(projection.entries[1]["_history_kind"], "event")
        self.assertEqual(projection.resolve_rewind_reference("2"), "2")

    def test_history_can_show_identity_timestamp_and_message_id(self):
        history = [{
            "Q": '[群聊发言者] {"id": "onebot.v11:user:42", "name": "小明"}\n你好',
            "A": "你好。",
            "created_at": "2026-07-19T14:37:14.567943",
            "message_id": "message-42",
        }]

        text = history_views.format_history(history, show_message_id=True)

        self.assertIn("ID: onebot.v11:user:42", text)
        self.assertIn("2026-07-19 14:37", text)
        self.assertIn("消息: message-42", text)

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

    def test_history_normalizes_private_citations_and_plain_text(self):
        raw = "王勃是作者。\ue200cite\ue202turn0search11\ue201\n\n**重点**：[百科](https://example.com)"

        markdown = history_views.normalize_history_markdown(raw)
        plain_text = history_views.history_plain_text(raw)

        self.assertNotIn("turn0search11", markdown)
        self.assertIn("**重点**", markdown)
        self.assertNotIn("**", plain_text)
        self.assertIn("百科 (https://example.com)", plain_text)

    def test_history_link_replacement_keeps_link_metadata_at_the_call_site(self):
        replaced = history_views.replace_history_links(
            "[百科](https://example.com)",
            lambda label, url: f"{label}[1]",
        )

        self.assertEqual(replaced, "百科[1]")
