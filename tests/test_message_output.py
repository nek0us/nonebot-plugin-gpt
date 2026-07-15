import unittest
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

from nonebot_plugin_alconna.uniseg import UniMessage


_MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "message_output.py"
_PACKAGE_PATH = _MODULE_PATH.parent
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(_PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
_SPEC = importlib.util.spec_from_file_location("nonebot_plugin_gpt.message_output", _MODULE_PATH)
assert _SPEC and _SPEC.loader
message_output = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = message_output
_SPEC.loader.exec_module(message_output)
finish_message = message_output.finish_message
finish_image_pages = message_output.finish_image_pages
TextPages = message_output.TextPages


class _Matcher:
    def __init__(self):
        self.finish = AsyncMock()


class MessageOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_unimessage_is_sent_through_its_adapter_exporter(self):
        matcher = _Matcher()
        event = object()
        message = UniMessage.text("test")
        message.send = AsyncMock()

        await finish_message(matcher, event, message)

        message.send.assert_awaited_once_with(event)
        matcher.finish.assert_awaited_once_with()

    async def test_plain_text_is_sent_by_matcher(self):
        matcher = _Matcher()

        await finish_message(matcher, object(), "test")

        matcher.finish.assert_awaited_once_with("test")

    async def test_pages_are_sent_individually(self):
        matcher = _Matcher()
        event = object()
        original_send = UniMessage.send
        send = AsyncMock()
        UniMessage.send = send
        try:
            await finish_message(matcher, event, TextPages(("第一页", "第二页")))
        finally:
            UniMessage.send = original_send

        self.assertEqual(send.await_count, 2)
        matcher.finish.assert_awaited_once_with()

    async def test_only_multi_page_management_output_schedules_recall(self):
        matcher = _Matcher()
        event = object()
        original_send = UniMessage.send
        UniMessage.send = AsyncMock(return_value=object())
        try:
            with patch.object(message_output, "_schedule_recall") as schedule:
                await finish_message(
                    matcher,
                    event,
                    TextPages(("第一页", "第二页")),
                    recall_after=60,
                )
        finally:
            UniMessage.send = original_send

        self.assertEqual(schedule.call_count, 2)
        self.assertTrue(all(call.args[1] == 60 for call in schedule.call_args_list))

    async def test_image_pages_prefer_a_single_reference_message(self):
        matcher = _Matcher()
        original_send = UniMessage.send
        send = AsyncMock(return_value=object())
        UniMessage.send = send
        try:
            with patch.object(message_output, "_schedule_recall") as schedule:
                await finish_image_pages(
                    matcher,
                    object(),
                    (b"first", b"second"),
                    title="聊天记录",
                    recall_after=60,
                )
        finally:
            UniMessage.send = original_send

        send.assert_awaited_once()
        schedule.assert_called_once_with(send.return_value, 60)
        matcher.finish.assert_awaited_once_with()

    async def test_image_pages_fall_back_to_individual_images(self):
        matcher = _Matcher()
        original_send = UniMessage.send
        receipt = object()
        send = AsyncMock(side_effect=(RuntimeError("unsupported"), receipt, receipt))
        UniMessage.send = send
        try:
            await finish_image_pages(
                matcher,
                object(),
                (b"first", b"second"),
                title="聊天记录",
            )
        finally:
            UniMessage.send = original_send

        self.assertEqual(send.await_count, 3)
        matcher.finish.assert_awaited_once_with()
