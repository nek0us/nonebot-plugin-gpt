import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
tables = importlib.import_module("nonebot_plugin_gpt.table_documents")


class TableDocumentTests(unittest.TestCase):
    def test_table_escapes_cells_and_keeps_page_metadata(self):
        pages = tables.build_table_pages(
            "白名单列表",
            ("类型", "标识"),
            (("会话", "<scope&one>"),),
        )

        self.assertEqual(len(pages), 1)
        self.assertIn("&lt;scope&amp;one&gt;", pages[0].html)
        self.assertEqual(pages[0].index, 1)
        self.assertEqual(pages[0].total, 1)
        self.assertIn("<table>", pages[0].html)
        self.assertIn("#8c75d9", pages[0].html)
        self.assertIn("#fff9fc", pages[0].html)

    def test_table_splits_long_lists_into_multiple_pages(self):
        pages = tables.build_table_pages(
            "人设列表",
            ("序号", "名称"),
            ((index, f"人设 {index}") for index in range(30)),
            rows_per_page=10,
        )

        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[1].index, 2)
        self.assertEqual(pages[1].total, 3)

    def test_whitelist_table_marks_paid_sessions(self):
        pages = tables.whitelist_table_pages(
            {"sessions": ["group:1"], "users": ["user:1"]},
            {"group:1": True},
        )

        self.assertIn("Plus", pages[0].html)
        self.assertIn("个人", pages[0].html)

    def test_persona_table_shows_newest_first_without_renumbering(self):
        personality = type("Personality", (), {
            "init_list": [{"name": "旧人设"}, {"name": "中间人设"}, {"name": "新人设"}],
        })()

        pages = tables.persona_table_pages(personality, {})

        self.assertEqual(pages[0].rows[0][:2], ("3", "新人设"))
        self.assertEqual(pages[0].rows[-1][:2], ("1", "旧人设"))

    def test_access_tables_show_newest_entries_first(self):
        blacklist = tables.blacklist_table_pages({"旧目标": ["旧原因"], "新目标": ["新原因"]})
        whitelist = tables.whitelist_table_pages(
            {"sessions": ["会话:旧", "会话:新"], "users": ["用户:旧", "用户:新"]},
            {},
        )

        self.assertEqual(blacklist[0].rows[0][0], "新目标")
        self.assertEqual(whitelist[0].rows[:2], (("会话", "会话:新", "普通"), ("会话", "会话:旧", "普通")))

    def test_cdk_table_orders_records_by_created_time_descending(self):
        pages = tables.cdk_table_pages((
            {"code": "old", "status": "available", "created_at": "2026-01-01T00:00:00+00:00"},
            {"code": "new", "status": "available", "created_at": "2026-01-02T00:00:00+00:00"},
        ))

        self.assertEqual(pages[0].rows[0][0], "new")

    def test_session_table_shows_creator_titles_and_times(self):
        state = type("State", (), {
            "logical_id": "logical-1",
            "label": "本地首句",
            "original_title": "网页原始标题",
            "creator_id": "1130131059",
            "creator_name": "nekous",
            "persona_name": "猪咪",
            "model": "gpt-5",
            "checkpoints": [object()],
            "created_at": "2026-07-19T06:37:14+00:00",
            "updated_at": "2026-07-20T07:38:15+00:00",
            "metadata": {"upstream_created_at": 1_700_000_000},
        })()

        pages = tables.session_table_pages([state], "logical-1")

        self.assertEqual(pages[0].columns, ("序号", "状态", "会话详情", "创建者", "时间"))
        self.assertIn("网页原始标题", pages[0].rows[0][2])
        self.assertIn("本地首句", pages[0].rows[0][2])
        self.assertEqual(pages[0].rows[0][3], "nekous（1130131059）")
        self.assertIn("2026-07-19 14:37", pages[0].rows[0][4])
        self.assertIn("<colgroup>", pages[0].html)
