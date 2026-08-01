import importlib
import sys
import types
import unittest
from pathlib import Path

from ChatGPTWeb.config import IOFile


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

    async def test_image_output_appends_copyable_references_after_the_image(self):
        async def renderer(_markdown: str) -> bytes:
            return b"image"

        message = await output.build_unimessage(
            rendering.RenderPlan(
                text="文本",
                markdown="# 标题\n\n百科[1]",
                markdown_image_required=True,
                reference_text="参考链接\n[1] 百科\nhttps://example.com/a",
            ),
            render_markdown=renderer,
        )

        self.assertIn("https://example.com/a", message.extract_plain_text())

    async def test_native_markdown_output_uses_uniseg_styles_without_rendering_an_image(self):
        message = await output.build_unimessage(
            rendering.RenderPlan(
                text="重点 百科 (https://example.com)",
                markdown="**重点** [百科](https://example.com)",
                native_markdown=True,
            ),
        )

        self.assertNotIn("**", message.extract_plain_text())
        self.assertTrue(any(
            "link" in style
            for segment in message
            for style in segment.styles.values()
        ))

    async def test_generated_files_use_native_file_and_image_segments(self):
        message = await output.build_unimessage(
            rendering.RenderPlan(
                text="done",
                files=[
                    IOFile(content=b"report", name="report.txt", mime_type="text/plain"),
                    IOFile(
                        content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                        name="preview.png",
                        mime_type="image/png",
                    ),
                ],
            ),
        )

        segments = [(segment.type, segment.name, segment.raw) for segment in message if segment.type in {"file", "image"}]
        self.assertEqual(segments, [
            ("file", "report.txt", b"report"),
            ("image", "preview.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"),
        ])
