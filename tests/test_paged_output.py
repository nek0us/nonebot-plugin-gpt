import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
paged_output = importlib.import_module("nonebot_plugin_gpt.paged_output")


class PagedOutputTests(unittest.TestCase):
    def test_short_text_stays_in_one_page(self):
        self.assertEqual(paged_output.paginate_text("状态正常").pages, ("状态正常",))

    def test_long_text_is_split_with_page_markers(self):
        text = "\n".join(f"第 {index} 条记录" for index in range(600))
        pages = paged_output.paginate_text(text, limit=100).pages

        self.assertGreater(len(pages), 1)
        self.assertTrue(pages[0].endswith(f"[1/{len(pages)}]"))
        self.assertLessEqual(max(map(len, pages)), 110)
