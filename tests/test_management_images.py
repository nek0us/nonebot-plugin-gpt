import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
management_images = importlib.import_module("nonebot_plugin_gpt.management_images")


class ManagementImageTests(unittest.TestCase):
    def test_status_image_uses_remote_core_summary_without_account_details(self):
        html = management_images.build_account_status_html({
            "account_summary": {"configured": 4, "available": 3, "attention": 1},
            "accounts": [{"email": "shared-core", "available": True, "shared_core": True}],
        })

        self.assertIn('metric-value">4', html)
        self.assertIn('metric-value">3', html)
        self.assertIn("共享核心", html)
        self.assertNotIn("shared-core", html)

    def test_help_image_keeps_the_requested_topic_and_commands(self):
        html = management_images.build_help_html("会话")

        self.assertIn("GPT 帮助 - 会话", html)
        self.assertIn("切换会话", html)
        self.assertNotIn("NONEBOT PLUGIN", html)
        self.assertNotIn("nonebot-plugin-gpt", html)
        self.assertIn("border-left: 7px solid #8c75d9", html)

    def test_default_help_image_includes_cdk_onboarding(self):
        html = management_images.build_help_html()

        self.assertIn("先向机器人管理员领取 CDK", html)
        self.assertIn("兑换 &lt;CDK&gt;", html)

    def test_status_image_has_summary_and_safe_account_details(self):
        html = management_images.build_account_status_html({
            "accounts": [{
                "email": "account@example.com",
                "available": True,
                "account_plan": "plus",
                "status": "Ready",
                "conversation_count": 2,
                "observed_model_count": 3,
                "usage": {"requests": 5},
                "runtime": {"context_ready": True},
            }],
        })

        self.assertIn("当前可用", html)
        self.assertIn("account@example.com", html)
        self.assertIn("套餐 Plus", html)
        self.assertIn("本进程请求 5", html)

    def test_status_image_includes_capability_budget(self):
        html = management_images.build_account_status_html({
            "accounts": [{
                "email": "account@example.com",
                "available": True,
                "status": "Ready",
                "capability_quota": {
                    "enabled": True,
                    "upload_total": 1,
                    "image_upload": {"used": 1, "budget_used": 1, "limit": 2},
                    "file_upload": {"used": 0, "budget_used": 1, "limit": 2},
                    "image_generation": {
                        "used": 1,
                        "budget_used": 1,
                        "limit": 2,
                    },
                },
            }],
        })

        self.assertIn("高级能力（本地估算）：上传 1/2", html)
        self.assertIn("生图 1/2", html)
