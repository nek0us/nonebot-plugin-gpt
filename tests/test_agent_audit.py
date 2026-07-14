import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
audit = importlib.import_module("nonebot_plugin_gpt.agent_audit")


class AgentAuditTests(unittest.TestCase):
    def test_audit_is_bounded_and_does_not_require_user_content(self):
        log = audit.AgentAuditLog(limit=2)
        log.record("计划已创建", "环境", "本机只读")
        log.record("工具已执行", "环境", "本机只读")
        log.record("确认已取消", "演示", "本机只读")

        text = log.format()

        self.assertNotIn("计划已创建", text)
        self.assertIn("工具已执行", text)
        self.assertIn("确认已取消", text)
        self.assertNotIn("任务原文", text)
