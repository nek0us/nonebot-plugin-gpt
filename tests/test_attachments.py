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

    async def test_remote_image_uses_nonebot_driver_http_client(self):
        class Response:
            status_code = 200
            content = b"remote-image"

        class Client:
            def __init__(self):
                self.requests = []

            async def request(self, request):
                self.requests.append(request)
                return Response()

        class Session:
            def __init__(self, client):
                self.client = client

            async def __aenter__(self):
                return self.client

            async def __aexit__(self, *args):
                return None

        class Driver:
            def __init__(self):
                self.client = Client()
                self.proxy = None

            def get_session(self, *, proxy=None):
                self.proxy = proxy
                return Session(self.client)

        driver = Driver()
        original_driver = attachments.get_driver
        original_mixin = attachments.HTTPClientMixin
        attachments.get_driver = lambda: driver
        attachments.HTTPClientMixin = Driver
        try:
            class Segment:
                type = "image"
                data = {"url": "https://example.test/photo.png?size=large"}

            files = await attachments.extract_image_files([Segment()], proxy="http://127.0.0.1:7890")
        finally:
            attachments.get_driver = original_driver
            attachments.HTTPClientMixin = original_mixin

        self.assertEqual(driver.proxy, "http://127.0.0.1:7890")
        self.assertEqual(driver.client.requests[0].method, "GET")
        self.assertEqual(str(driver.client.requests[0].url), "https://example.test/photo.png?size=large")
        self.assertEqual(files[0].name, "photo.png")
        self.assertEqual(files[0].content, b"remote-image")
