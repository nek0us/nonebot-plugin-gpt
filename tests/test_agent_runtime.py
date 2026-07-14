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
agent_runtime = importlib.import_module("nonebot_plugin_gpt.agent_runtime")
agent_planner = importlib.import_module("nonebot_plugin_gpt.agent_planner")


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

    async def send(self, request):
        self.plan_request = request
        return ChatResult(
            ok=True,
            text='{"tool":"环境","reason":"需要查看当前系统信息。"}',
            conversation_id="",
            message_id="",
        )


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_tools_are_read_only_and_do_not_refresh_remote_catalog(self):
        service = _Service()
        runtime = agent_runtime.create_agent_runtime(service)

        self.assertIn("状态", runtime.help_text())
        self.assertIn("模型", runtime.help_text())
        self.assertIn("本机只读", runtime.help_text())
        self.assertIn("ChatGPT 运行状态", await runtime.execute("状态", operator_id="admin", scope_id="private:1"))
        self.assertIn("免费模型", await runtime.execute("模型", operator_id="admin", scope_id="private:1"))
        self.assertFalse(service.fetch_remote)

    async def test_unknown_tool_does_not_execute_anything(self):
        runtime = agent_runtime.create_agent_runtime(_Service())

        self.assertIn("未找到", await runtime.execute("重启机器", operator_id="admin", scope_id="private:1"))

    async def test_model_plan_is_validated_but_not_executed(self):
        service = _Service()
        runtime = agent_runtime.create_agent_runtime(service)

        text = await runtime.execute("计划 检查系统", operator_id="admin", scope_id="private:1")

        self.assertIn("智能体计划（未执行）", text)
        self.assertIn("建议工具：环境", text)
        self.assertIn("只输出一个 JSON", service.plan_request.prompt)

    async def test_plan_execution_is_scoped_and_single_use(self):
        calls = []

        class _Planner:
            async def plan(self, task, tools):
                return agent_planner.AgentPlan("演示", "执行测试只读工具。", True)

        runtime = agent_runtime.AgentRuntime(
            [agent_runtime.AgentTool(
                "演示",
                "测试只读工具",
                agent_runtime.AgentPermission.READ_LOCAL,
                agent_runtime.AgentApproval.AUTOMATIC,
                lambda: self._record_call(calls),
            )],
            planner=_Planner(),
            token_factory=lambda: "plan",
        )

        planned = await runtime.execute("计划 执行测试", operator_id="admin", scope_id="group:1")
        self.assertIn("执行 plan", planned)
        self.assertIn(
            "原操作者",
            await runtime.execute("执行 plan", operator_id="other", scope_id="group:1"),
        )
        self.assertEqual("已执行", await runtime.execute("执行 plan", operator_id="admin", scope_id="group:1"))
        self.assertEqual(calls, ["called"])
        self.assertIn(
            "未找到",
            await runtime.execute("执行 plan", operator_id="admin", scope_id="group:1"),
        )

    async def test_confirmation_is_bound_to_operator_scope_and_expiry(self):
        calls = []
        now = [100.0]
        runtime = agent_runtime.AgentRuntime(
            [agent_runtime.AgentTool(
                "演示",
                "测试工具",
                agent_runtime.AgentPermission.PROCESS_CONTROL,
                agent_runtime.AgentApproval.CONFIRM,
                lambda: self._record_call(calls),
            )],
            confirmation_ttl_seconds=10,
            clock=lambda: now[0],
            token_factory=lambda: "pending",
        )

        requested = await runtime.execute("演示", operator_id="admin", scope_id="group:1")
        self.assertIn("确认 pending", requested)
        self.assertIn("进程控制", requested)
        self.assertEqual(calls, [])
        self.assertIn(
            "原操作者",
            await runtime.execute("确认 pending", operator_id="other", scope_id="group:1"),
        )
        self.assertEqual("已执行", await runtime.execute("确认 pending", operator_id="admin", scope_id="group:1"))
        self.assertEqual(calls, ["called"])

        await runtime.execute("演示", operator_id="admin", scope_id="group:1")
        now[0] += 11
        self.assertIn(
            "过期",
            await runtime.execute("确认 pending", operator_id="admin", scope_id="group:1"),
        )
        self.assertEqual(calls, ["called"])

    async def test_low_risk_authorization_is_scoped_and_revocable(self):
        calls = []
        tokens = iter(("grant", "action"))
        runtime = agent_runtime.AgentRuntime(
            [agent_runtime.AgentTool(
                "演示",
                "测试工具",
                agent_runtime.AgentPermission.READ_LOCAL,
                agent_runtime.AgentApproval.CONFIRM,
                lambda: self._record_call(calls),
            )],
            confirmation_ttl_seconds=10,
            session_approval_ttl_seconds=30,
            token_factory=lambda: next(tokens),
        )

        requested = await runtime.execute("授权 本机只读", operator_id="admin", scope_id="group:1")
        self.assertIn("确认 grant", requested)
        self.assertIn("本机只读", requested)
        self.assertIn(
            "原操作者",
            await runtime.execute("确认 grant", operator_id="other", scope_id="group:1"),
        )
        self.assertIn(
            "已授予",
            await runtime.execute("确认 grant", operator_id="admin", scope_id="group:1"),
        )
        self.assertIn("本机只读", await runtime.execute("授权列表", operator_id="admin", scope_id="group:1"))
        self.assertEqual("已执行", await runtime.execute("演示", operator_id="admin", scope_id="group:1"))
        self.assertEqual(calls, ["called"])

        self.assertIn("已撤销", await runtime.execute("撤销授权", operator_id="admin", scope_id="group:1"))
        self.assertIn("确认 action", await runtime.execute("演示", operator_id="admin", scope_id="group:1"))

    async def _record_call(self, calls):
        calls.append("called")
        return "已执行"


if __name__ == "__main__":
    unittest.main()
