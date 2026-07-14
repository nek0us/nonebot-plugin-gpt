import unittest
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock

from nonebot_plugin_alconna.uniseg import UniMessage


_MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "message_output.py"
_SPEC = importlib.util.spec_from_file_location("nonebot_plugin_gpt_message_output", _MODULE_PATH)
assert _SPEC and _SPEC.loader
message_output = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = message_output
_SPEC.loader.exec_module(message_output)
finish_message = message_output.finish_message


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
