import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
agent_runtime = importlib.import_module("nonebot_plugin_gpt.agent_runtime")


class _Service:
    async def get_account_status(self):
        return {"accounts": [{"email": "account@example.test", "available": True, "status": "Ready"}]}

    async def get_model_catalog(self, fetch_remote: bool = True):
        self.fetch_remote = fetch_remote
        return {
            "local": {
                "free": {"auto": "auto"},
                "plus": {"gpt5": "gpt-5"},
            },
        }


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_tools_are_read_only_and_do_not_refresh_remote_catalog(self):
        service = _Service()
        runtime = agent_runtime.create_agent_runtime(service)

        self.assertIn("状态", runtime.help_text())
        self.assertIn("模型", runtime.help_text())
        self.assertIn("ChatGPT 运行状态", await runtime.execute("状态"))
        self.assertIn("免费模型", await runtime.execute("模型"))
        self.assertFalse(service.fetch_remote)

    async def test_unknown_tool_does_not_execute_anything(self):
        runtime = agent_runtime.create_agent_runtime(_Service())

        self.assertIn("未找到", await runtime.execute("重启机器"))


if __name__ == "__main__":
    unittest.main()
