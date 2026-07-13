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
                "observed_model_count": 3,
                "usage": {"requests": 7},
                "runtime": {"context_ready": True, "page_ready": True},
            }],
        })

        self.assertIn("account@example.test", text)
        self.assertIn("账户 1 个｜可用 1 个｜需处理 0 个", text)
        self.assertIn("套餐 免费版", text)
        self.assertIn("本进程请求 7 次", text)
        self.assertIn("上下文已就绪，页面已就绪", text)
        self.assertNotIn("password", text)

    def test_status_highlights_manual_action_without_raw_error(self):
        text = management_views.format_account_status({
            "accounts": [
                {
                    "email": "verify@example.test",
                    "status": "Stop",
                    "available": False,
                    "account_plan": "plus",
                    "verification": {"code": "123456"},
                    "last_login_error": "sensitive browser details",
                },
                {
                    "email": "paused@example.test",
                    "status": "Stop",
                    "available": False,
                    "manual_disabled": True,
                    "login_failure_kind": "bad_credentials",
                },
            ],
        })

        self.assertIn("账户 2 个｜可用 0 个｜需处理 2 个", text)
        self.assertIn("等待人工完成登录验证", text)
        self.assertIn("已由管理员停用", text)
        self.assertNotIn("123456", text)
        self.assertNotIn("sensitive browser details", text)
