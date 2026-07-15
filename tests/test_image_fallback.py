import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
fallback = importlib.import_module("nonebot_plugin_gpt.image_fallback")


@unittest.skipUnless(fallback.use_local_font_renderer(), "仅在具备本地中文字体时验证图片渲染")
class ImageFallbackTests(unittest.TestCase):
    def test_markdown_renderer_produces_a_png(self):
        image = fallback.render_markdown_page("# 聊天记录\n\n## 第 1 轮\n\n你好")

        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_table_renderer_produces_a_png(self):
        tables = importlib.import_module("nonebot_plugin_gpt.table_documents")
        page = tables.build_table_pages("白名单列表", ("类型", "标识"), (("会话", "scope:1"),))[0]

        image = fallback.render_table_page(page)

        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
