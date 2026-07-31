import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path

from aiohttp import web


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
attachments = importlib.import_module("nonebot_plugin_gpt.attachments")


class AttachmentTests(unittest.IsolatedAsyncioTestCase):
    async def _serve(self, routes):
        app = web.Application()
        for method, path, handler in routes:
            app.router.add_route(method, path, handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        port = site._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def test_unimessage_image_is_extracted_without_adapter_conversion(self):
        from nonebot_plugin_alconna.uniseg import Image, UniMessage

        files = await attachments.extract_image_files(
            UniMessage([Image(raw=b"image-data", name="cat.png")]),
        )

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "cat.png")
        self.assertEqual(files[0].content, b"image-data")

    async def test_unimessage_file_is_extracted_when_enabled(self):
        from nonebot_plugin_alconna.uniseg import File, UniMessage

        files = await attachments.extract_upload_files(
            UniMessage([File(raw=b"document-data", name="notes.txt")]),
            upload_images=False,
            upload_files=True,
            max_file_size=1024,
        )

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "notes.txt")
        self.assertEqual(files[0].content, b"document-data")

    async def test_attachment_filename_is_reduced_to_a_safe_basename(self):
        from nonebot_plugin_alconna.uniseg import File, UniMessage

        files = await attachments.extract_upload_files(
            UniMessage([File(raw=b"data", name="../../unsafe?.txt")]),
            upload_images=False,
            upload_files=True,
            max_file_size=1024,
        )

        self.assertEqual(files[0].name, "unsafe_.txt")

    async def test_local_attachment_requires_an_allowed_root(self):
        from nonebot_plugin_alconna.uniseg import File, UniMessage

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notes.txt"
            source.write_bytes(b"local-data")
            message = UniMessage([File(path=source)])

            blocked = await attachments.extract_upload_files(
                message,
                upload_images=False,
                upload_files=True,
                max_file_size=1024,
            )
            allowed = await attachments.extract_upload_files(
                message,
                upload_images=False,
                upload_files=True,
                max_file_size=1024,
                allowed_local_roots=[directory],
            )

        self.assertEqual(blocked, [])
        self.assertEqual(allowed[0].content, b"local-data")
        self.assertEqual(allowed[0].name, "notes.txt")

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

    async def test_remote_image_is_streamed_from_an_explicitly_allowed_host(self):
        async def photo(_request):
            return web.Response(
                body=b"remote-image",
                headers={"Content-Disposition": 'attachment; filename="photo.png"'},
            )

        base_url = await self._serve([("GET", "/photo", photo)])

        class Segment:
            type = "image"
            data = {"url": f"{base_url}/photo?size=large"}

        files = await attachments.extract_upload_files(
            [Segment()],
            upload_images=True,
            upload_files=False,
            max_file_size=1024,
            allowed_hosts=["127.0.0.1"],
        )

        self.assertEqual(files[0].name, "photo.png")
        self.assertEqual(files[0].content, b"remote-image")

    async def test_private_remote_image_is_blocked_by_default(self):
        requested = False

        async def photo(_request):
            nonlocal requested
            requested = True
            return web.Response(body=b"private-image")

        base_url = await self._serve([("GET", "/photo", photo)])

        class Segment:
            type = "image"
            data = {"url": f"{base_url}/photo"}

        files = await attachments.extract_upload_files(
            [Segment()],
            upload_images=True,
            upload_files=False,
            max_file_size=1024,
        )

        self.assertEqual(files, [])
        self.assertFalse(requested)

    async def test_redirect_target_is_validated_again(self):
        target_requested = False

        async def redirect(request):
            port = request.url.port
            raise web.HTTPFound(f"http://localhost:{port}/photo")

        async def photo(_request):
            nonlocal target_requested
            target_requested = True
            return web.Response(body=b"private-image")

        base_url = await self._serve([
            ("GET", "/redirect", redirect),
            ("GET", "/photo", photo),
        ])

        class Segment:
            type = "image"
            data = {"url": f"{base_url}/redirect"}

        files = await attachments.extract_upload_files(
            [Segment()],
            upload_images=True,
            upload_files=False,
            max_file_size=1024,
            allowed_hosts=["127.0.0.1"],
        )

        self.assertEqual(files, [])
        self.assertFalse(target_requested)

    async def test_stream_without_content_length_stops_at_size_limit(self):
        async def oversized(request):
            response = web.StreamResponse()
            response.enable_chunked_encoding()
            await response.prepare(request)
            await response.write(b"a" * 700)
            await response.write(b"b" * 700)
            await response.write_eof()
            return response

        base_url = await self._serve([("GET", "/large", oversized)])

        class Segment:
            type = "image"
            data = {"url": f"{base_url}/large"}

        files = await attachments.extract_upload_files(
            [Segment()],
            upload_images=True,
            upload_files=False,
            max_file_size=1024,
            allowed_hosts=["127.0.0.1"],
        )

        self.assertEqual(files, [])

    async def test_total_attachment_size_is_enforced(self):
        from nonebot_plugin_alconna.uniseg import File, UniMessage

        files = await attachments.extract_upload_files(
            UniMessage([
                File(raw=b"a" * 600, name="first.bin"),
                File(raw=b"b" * 600, name="second.bin"),
            ]),
            upload_images=False,
            upload_files=True,
            max_file_size=1024,
            max_total_size=1000,
        )

        self.assertEqual([item.name for item in files], ["first.bin"])
