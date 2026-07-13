import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
plus_views = importlib.import_module("nonebot_plugin_gpt.plus_views")


class PlusViewTests(unittest.TestCase):
    def test_grant_and_revoke_paid_access(self):
        settings = {"status": True}

        self.assertIn("添加", plus_views.grant_paid_access(settings, "group-1"))
        self.assertEqual(settings["group-1"], "auto")
        self.assertIn("删除", plus_views.revoke_paid_access(settings, "group-1"))
        self.assertNotIn("group-1", settings)

    def test_global_switch_accepts_chinese_values(self):
        settings = {"status": True}

        message = plus_views.set_global_paid_enabled(settings, "关闭")

        self.assertFalse(settings["status"])
        self.assertIn("关闭", message)
