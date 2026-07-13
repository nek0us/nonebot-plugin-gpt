import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
attachments = importlib.import_module("nonebot_plugin_gpt.attachments")


class AttachmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_segments_without_http_image_urls_are_ignored(self):
        class Segment:
            def __init__(self, segment_type, data):
                self.type = segment_type
                self.data = data

        files = await attachments.extract_image_files([
            Segment("text", {}),
            Segment("image", {"url": "file:///tmp/example.png"}),
        ])

        self.assertEqual(files, [])

    async def test_unified_image_with_raw_bytes_is_preserved(self):
        image = attachments.Image(raw=b"image-bytes", name="upload.png")
        original = attachments.UniMessage.of
        attachments.UniMessage.of = lambda _message: attachments.UniMessage(image)
        try:
            files = await attachments.extract_image_files([])
        finally:
            attachments.UniMessage.of = original

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "upload.png")
        self.assertEqual(files[0].content, b"image-bytes")
