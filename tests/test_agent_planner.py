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
planner = importlib.import_module("nonebot_plugin_gpt.agent_planner")


class _Service:
    async def send(self, request):
        self.request = request
        return ChatResult(
            ok=True,
            text='{"tool":"环境","reason":"需要先获取系统概况。"}',
            conversation_id="",
            message_id="",
        )


class AgentPlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_planner_only_accepts_registered_tool(self):
        service = _Service()
        result = await planner.AgentPlanner(service).plan("检查机器", [{
            "name": "环境",
            "description": "查看环境",
            "permission": "本机只读",
            "approval": "自动允许",
            "parameters": [],
        }])

        self.assertTrue(result.valid)
        self.assertEqual(result.tool_name, "环境")
        self.assertIn("只输出一个 JSON", service.request.prompt)

    async def test_unregistered_model_tool_is_rejected(self):
        result = planner.parse_agent_plan(
            '{"tool":"执行命令","reason":"运行 shell"}',
            {"环境"},
        )

        self.assertFalse(result.valid)
        self.assertIn("未注册", result.error)

    async def test_non_json_model_response_is_rejected(self):
        result = planner.parse_agent_plan("请运行命令", {"环境"})

        self.assertFalse(result.valid)
        self.assertIn("JSON", result.error)

    async def test_plan_arguments_must_be_string_object(self):
        result = planner.parse_agent_plan(
            '{"tool":"环境","reason":"测试","arguments":{"limit":1}}',
            {"环境"},
        )

        self.assertFalse(result.valid)
        self.assertIn("参数", result.error)

    def test_plan_summary_is_optional_and_bounded(self):
        result = planner.parse_agent_plan(
            '{"tool":"环境","summary":"' + "甲" * 200 + '","reason":"测试"}',
            {"环境"},
        )

        self.assertTrue(result.valid)
        self.assertEqual(len(result.summary), 160)


if __name__ == "__main__":
    unittest.main()
