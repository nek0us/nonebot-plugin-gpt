import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
output = importlib.import_module("nonebot_plugin_gpt.unimessage_output")
rendering = importlib.import_module("nonebot_plugin_gpt.rendering")


class UniMessageOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_markdown_renderer_falls_back_to_text(self):
        async def broken_renderer(_markdown: str) -> bytes:
            raise RuntimeError("template missing")

        message = await output.build_unimessage(
            rendering.RenderPlan(
                text="纯文本回退",
                markdown="# 标题",
                markdown_image_required=True,
            ),
            render_markdown=broken_renderer,
        )

        self.assertIn("纯文本回退", message.extract_plain_text())
