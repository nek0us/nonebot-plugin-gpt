import importlib
import sys
import types
import unittest
from pathlib import Path

from ChatGPTWeb import ChatResult


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
diagnostics = importlib.import_module("nonebot_plugin_gpt.failure_diagnostics")


class FailureDiagnosticsTests(unittest.TestCase):
    def test_summary_only_keeps_safe_categories(self):
        tracker = diagnostics.ChatFailureDiagnostics()
        tracker.record_result(ChatResult(
            ok=False,
            text="internal reply",
            conversation_id="",
            message_id="",
            errors=[{"kind": "continue_chat_timeout", "message": "secret upstream detail"}],
        ))
        tracker.record_exception()

        text = tracker.format()

        self.assertIn("启动或请求超时 1", text)
        self.assertIn("插件运行异常 1", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("internal reply", text)
