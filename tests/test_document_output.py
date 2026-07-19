import importlib
import asyncio
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
        self.assertIn("onebot.v11:user:42", pages[0])
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

    def test_history_card_renders_markdown_and_hides_private_citations(self):
        pages = document_output.build_history_pages([
            {"Q": "介绍一下", "A": "**王勃**是作者。\ue200cite\ue202turn0search11\ue201\n\n[百科](https://example.com)\n\n---\n\n- 第一项"},
        ])

        html = pages[0].html

        self.assertIn("<strong>王勃</strong>", html)
        self.assertIn("百科[1]", html)
        self.assertIn("参考链接", html)
        self.assertIn("example.com", html)
        self.assertNotIn('href="https://example.com"', html)
        self.assertIn("<hr", html)
        self.assertIn("<li>第一项</li>", html)
        self.assertNotIn("turn0search11", html)

    def test_history_event_uses_a_distinct_card_and_metadata(self):
        pages = document_output.build_history_pages([
            {
                "Q": "提醒到时：吃饭",
                "A": "记得吃饭呀。",
                "_history_speaker": "提醒事件",
                "_history_kind": "event",
                "created_at": 1_700_000_000,
                "message_id": "message-42",
            },
        ], show_message_id=True)

        page = pages[0]
        self.assertEqual(page.rounds[0].speaker, "提醒事件")
        self.assertEqual(page.rounds[0].kind, "event")
        self.assertIn('class="card event"', page.html)
        self.assertIn("消息: message-42", page.html)

    def test_history_references_are_deduplicated_and_exported_as_plain_urls(self):
        pages = document_output.build_history_pages([
            {
                "Q": "问题",
                "A": "[百科](https://example.com/a) 和 [百科](https://example.com/a)",
            },
        ])

        self.assertEqual(len(pages[0].links), 1)
        self.assertEqual(pages[0].links[0].index, 1)
        self.assertIn("百科[1]", pages[0].rounds[0].answer)
        self.assertEqual(
            document_output.history_reference_text(pages),
            "参考链接\n[1] 百科\nhttps://example.com/a",
        )

    def test_management_document_uses_the_shared_light_theme(self):
        html = document_output.build_document_html(
            "# 人设详情\n\n## 说明\n\n- 一条内容",
            font_scale=1.1,
        )

        self.assertIn('class="document"', html)
        self.assertIn("#8c75d9", html)
        self.assertIn("#e58ab0", html)
        self.assertIn("width: 760px", html)
        self.assertIn("--gpt-image-font-scale: 1.10", html)
        self.assertNotIn("NONEBOT PLUGIN", html)

    def test_history_renderer_passes_font_scale_to_local_renderer(self):
        pages = document_output.build_history_pages([{"Q": "你好", "A": "你好呀"}])
        original = document_output.use_local_font_renderer
        original_renderer = document_output.render_history_page
        received = []
        try:
            document_output.use_local_font_renderer = lambda: True
            document_output.render_history_page = lambda page, *, font_scale: received.append(font_scale) or b"image"
            images = asyncio.run(document_output.render_history_pages(pages, font_scale=1.15))
        finally:
            document_output.use_local_font_renderer = original
            document_output.render_history_page = original_renderer

        self.assertEqual(images, (b"image",))
        self.assertEqual(received, [1.15])
