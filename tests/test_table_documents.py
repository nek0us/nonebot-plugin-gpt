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
