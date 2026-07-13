import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
management_views = importlib.import_module("nonebot_plugin_gpt.management_views")


class ManagementViewTests(unittest.TestCase):
    def test_status_includes_safe_account_summary(self):
        text = management_views.format_account_status({
            "accounts": [{
                "email": "account@example.test",
                "status": "Ready",
                "available": True,
                "account_plan": "free",
                "conversation_count": 4,
                "login_guidance": "Ready.",
            }],
        })

        self.assertIn("account@example.test", text)
        self.assertIn("可用", text)
        self.assertNotIn("password", text)
