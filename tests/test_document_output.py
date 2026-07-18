import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
document_output = importlib.import_module("nonebot_plugin_gpt.document_output")


class DocumentOutputTests(unittest.TestCase):
    def test_history_keeps_question_and_answer_in_the_same_markdown_block(self):
        pages = document_output.build_history_markdown_pages([
            {"Q": "第一个问题", "A": "第一个回答"},
            {"Q": "第二个问题", "A": "第二个回答"},
        ])

        self.assertEqual(len(pages), 1)
        self.assertIn("## 第 1 轮", pages[0])
        self.assertIn("### 用户\n\n第一个问题", pages[0])
        self.assertIn("### 回复\n\n第一个回答", pages[0])

    def test_long_documents_are_paginated_with_page_markers(self):
        pages = document_output.build_markdown_pages(
            "白名单列表",
            [f"- 第 {index} 条白名单" for index in range(80)],
            page_limit=220,
        )

        self.assertGreater(len(pages), 1)
        self.assertTrue(all(page.startswith("# 白名单列表") for page in pages))
        self.assertIn(f"第 1 / {len(pages)} 页", pages[0])
        self.assertIn(f"第 {len(pages)} / {len(pages)} 页", pages[-1])

    def test_history_shows_group_speaker_name_without_internal_metadata(self):
        pages = document_output.build_history_markdown_pages([
            {
                "Q": '[群聊发言者] {"id":"onebot.v11:user:42","name":"小明"}\n你好',
                "A": "你好。",
            },
        ])

        self.assertIn("你好", pages[0])
        self.assertNotIn("群聊发言者", pages[0])
        self.assertNotIn("onebot.v11:user:42", pages[0])
        self.assertIn("用户 · 小明", pages[0])

    def test_very_long_history_round_keeps_a_labeled_continuation(self):
        pages = document_output.build_history_markdown_pages([
            {"Q": "问题", "A": "回答" * 400},
        ], page_limit=220)

        self.assertGreater(len(pages), 1)
        self.assertTrue(any("## 第 1 轮 · 回复续" in page for page in pages))

    def test_history_card_pages_keep_roles_and_hide_internal_branding(self):
        pages = document_output.build_history_pages([
            {"Q": "你好", "A": "你好呀"},
        ])

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].rounds[0].question, "你好")
        self.assertEqual(pages[0].rounds[0].answer, "你好呀")
        self.assertIn('class="card user"', pages[0].html)
        self.assertIn('class="card reply"', pages[0].html)
        self.assertNotIn("NONEBOT PLUGIN", pages[0].html)

    def test_history_card_pages_can_be_reversed_without_renumbering(self):
        pages = document_output.build_history_pages([
            {"Q": "第一问", "A": "第一答"},
            {"Q": "第二问", "A": "第二答"},
            {"Q": "第三问", "A": "第三答"},
        ], reverse_order=True)

        self.assertEqual(
            [round_item.number for round_item in pages[0].rounds],
            [3, 2, 1],
        )

    def test_management_document_uses_the_shared_light_theme(self):
        html = document_output.build_document_html("# 人设详情\n\n## 说明\n\n- 一条内容")

        self.assertIn('class="document"', html)
        self.assertIn("#8c75d9", html)
        self.assertIn("#e58ab0", html)
        self.assertNotIn("NONEBOT PLUGIN", html)
