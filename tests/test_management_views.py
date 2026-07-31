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
    def test_status_uses_remote_core_summary_without_exposing_accounts(self):
        text = management_views.format_account_status({
            "account_summary": {"configured": 4, "available": 3, "attention": 1},
            "accounts": [{"email": "shared-core", "available": True, "shared_core": True}],
        })

        self.assertIn("账户 4 个｜可用 3 个｜需处理 1 个", text)
        self.assertIn("共享核心（账户明细由核心控制台管理）", text)

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

    def test_status_includes_capability_budget_estimates(self):
        text = management_views.format_account_status({
            "accounts": [{
                "email": "account@example.test",
                "status": "Ready",
                "available": True,
                "capability_quota": {
                    "enabled": True,
                    "upload_total": 2,
                    "image_upload": {
                        "used": 1,
                        "budget_used": 2,
                        "limit": 3,
                    },
                    "file_upload": {
                        "used": 1,
                        "budget_used": 2,
                        "limit": 3,
                    },
                    "image_generation": {
                        "used": 2,
                        "budget_used": 2,
                        "limit": 2,
                        "limit_reason": "local_soft_budget",
                    },
                },
            }],
        })

        self.assertIn("高级能力（本地估算）：上传 2/3", text)
        self.assertIn("（图片 1，文件 1）", text)
        self.assertIn("生图 2/2", text)

    def test_remote_status_includes_coarse_capability_availability(self):
        text = management_views.format_account_status({
            "account_summary": {"configured": 3, "available": 2, "attention": 1},
            "accounts": [{
                "email": "shared-core",
                "available": True,
                "shared_core": True,
                "capability_quota": {
                    "shared_core": True,
                    "available_accounts": {
                        "image_upload": 2,
                        "file_upload": 1,
                        "image_generation": 2,
                    },
                },
            }],
        })

        self.assertIn("高级能力可用账号：图片 2，文件 1，生图 2", text)

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

    def test_status_can_include_safe_failure_summary(self):
        text = management_views.format_account_status({
            "accounts": [{
                "email": "account@example.test",
                "status": "Ready",
                "available": True,
            }],
        }, failure_summary="本次运行聊天失败 2 次（启动或请求超时 2）")

        self.assertIn("聊天失败汇总：本次运行聊天失败 2 次", text)
