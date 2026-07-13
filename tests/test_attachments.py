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
