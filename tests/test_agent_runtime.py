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

    async def test_direct_tool_exception_is_safely_reported(self):
        async def broken(_: dict[str, str]) -> str:
            raise RuntimeError("internal tool detail")

        runtime = agent_runtime.AgentRuntime([
            agent_runtime.AgentTool(
                "演示",
                "测试工具",
                agent_runtime.AgentPermission.READ_LOCAL,
                agent_runtime.AgentApproval.AUTOMATIC,
                broken,
            ),
        ])

        text = await runtime.execute("演示", operator_id="admin", scope_id="private:1")

        self.assertIn("未能完成", text)
        self.assertNotIn("internal tool detail", text)
        self.assertIn("工具执行失败", await runtime.execute("审计", operator_id="admin", scope_id="private:1"))

    async def test_managed_service_overview_requires_confirmation_when_tcp_is_configured(self):
        registry = agent_runtime.ManagedServiceRegistry.from_config([{
            "name": "api",
            "kind": "tcp",
            "host": "127.0.0.1",
            "port": 8080,
        }])
        runtime = agent_runtime.create_agent_runtime(_Service(), managed_services=registry)

        self.assertIn("受管服务概览", runtime.help_text())
        result = await runtime.execute("受管服务概览", operator_id="admin", scope_id="private:1")

        self.assertIn("网络读取", result)
        self.assertIn("智能体 确认", result)

    async def test_model_plan_is_validated_but_not_executed(self):
        service = _Service()
        runtime = agent_runtime.create_agent_runtime(service)

        text = await runtime.execute("计划 检查系统", operator_id="admin", scope_id="private:1")

        self.assertIn("智能体计划（未执行）", text)
        self.assertIn("建议动作：查看跨平台本机基础环境诊断", text)
        self.assertIn("参数：无", text)
        self.assertIn("摘要：需要查看当前系统信息。", text)
        self.assertIn("只输出一个 JSON", service.plan_request.prompt)

    async def test_sensitive_plan_parameters_are_redacted_in_display(self):
        class _Planner:
            async def plan(self, task, tools):
                return agent_planner.AgentPlan(
                    "演示",
                    "需要使用已验证的参数。",
                    True,
                    {"令牌": "private-value"},
                    summary="验证敏感参数展示。",
                )

        runtime = agent_runtime.AgentRuntime([
            agent_runtime.AgentTool(
                "演示",
                "执行受控演示",
                agent_runtime.AgentPermission.READ_LOCAL,
                agent_runtime.AgentApproval.AUTOMATIC,
                lambda _: self._record_call([]),
                parameters=(agent_runtime.AgentToolParameter("令牌", "访问令牌", sensitive=True),),
            ),
        ], planner=_Planner(), token_factory=lambda: "plan")

        text = await runtime.execute("计划 测试", operator_id="admin", scope_id="private:1")

        self.assertIn("参数：令牌：已提供", text)
        self.assertNotIn("private-value", text)

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
                lambda _: self._record_call(calls),
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
        executed = await runtime.execute("执行 plan", operator_id="admin", scope_id="group:1")
        self.assertIn("智能体执行结果", executed)
        self.assertIn("来源计划：plan", executed)
        self.assertIn("权限：本机只读", executed)
        self.assertIn("耗时：", executed)
        self.assertIn("已执行", executed)
        self.assertIn("状态：已完成", executed)
        self.assertEqual(calls, ["called"])
        self.assertIn("计划进入执行", await runtime.execute("审计", operator_id="admin", scope_id="group:1"))
        self.assertNotIn("执行测试", await runtime.execute("审计", operator_id="admin", scope_id="group:1"))
        self.assertIn(
            "未找到",
            await runtime.execute("执行 plan", operator_id="admin", scope_id="group:1"),
        )

    async def test_planned_tool_exception_is_safely_reported(self):
        class _Planner:
            async def plan(self, task, tools):
                return agent_planner.AgentPlan("演示", "测试失败回执。", True)

        async def broken(_: dict[str, str]) -> str:
            raise RuntimeError("internal planned detail")

        runtime = agent_runtime.AgentRuntime([
            agent_runtime.AgentTool(
                "演示",
                "测试工具",
                agent_runtime.AgentPermission.READ_LOCAL,
                agent_runtime.AgentApproval.AUTOMATIC,
                broken,
            ),
        ], planner=_Planner(), token_factory=lambda: "plan")

        await runtime.execute("计划 测试", operator_id="admin", scope_id="private:1")
        text = await runtime.execute("执行 plan", operator_id="admin", scope_id="private:1")

        self.assertIn("智能体执行结果", text)
        self.assertIn("状态：失败", text)
        self.assertNotIn("internal planned detail", text)
        self.assertIn("计划工具失败", await runtime.execute("审计", operator_id="admin", scope_id="private:1"))

    async def test_confirmed_plan_keeps_its_source_token_in_execution_receipt(self):
        class _Planner:
            async def plan(self, task, tools):
                return agent_planner.AgentPlan("重启", "需要执行受控操作。", True)

        runtime = agent_runtime.AgentRuntime(
            [agent_runtime.AgentTool(
                "重启",
                "执行受控重启",
                agent_runtime.AgentPermission.PROCESS_CONTROL,
                agent_runtime.AgentApproval.CONFIRM,
                lambda _: self._record_call([]),
            )],
            planner=_Planner(),
            token_factory=iter(("plan", "confirm")).__next__,
        )

        await runtime.execute("计划 重启服务", operator_id="admin", scope_id="private:1")
        pending = await runtime.execute("执行 plan", operator_id="admin", scope_id="private:1")
        self.assertIn("来源计划：plan（尚未执行）", pending)
        self.assertIn("确认 confirm", pending)

        result = await runtime.execute("确认 confirm", operator_id="admin", scope_id="private:1")
        self.assertIn("智能体执行结果", result)
        self.assertIn("来源计划：plan", result)
        self.assertIn("权限：进程控制", result)

    async def test_plan_arguments_are_validated_before_execution(self):
        calls = []

        class _Planner:
            async def plan(self, task, tools):
                return agent_planner.AgentPlan("演示", "测试参数校验。", True, {"level": "危险"})

        runtime = agent_runtime.AgentRuntime(
            [agent_runtime.AgentTool(
                "演示",
                "测试工具",
                agent_runtime.AgentPermission.READ_LOCAL,
                agent_runtime.AgentApproval.AUTOMATIC,
                lambda _: self._record_call(calls),
                parameters=(agent_runtime.AgentToolParameter(
                    "level",
                    "输出级别",
                    choices=("摘要", "详细"),
                ),),
            )],
            planner=_Planner(),
        )

        text = await runtime.execute("计划 测试参数", operator_id="admin", scope_id="private:1")

        self.assertIn("参数校验", text)
        self.assertEqual(calls, [])

    async def test_confirmation_is_bound_to_operator_scope_and_expiry(self):
        calls = []
        now = [100.0]
        runtime = agent_runtime.AgentRuntime(
            [agent_runtime.AgentTool(
                "演示",
                "测试工具",
                agent_runtime.AgentPermission.PROCESS_CONTROL,
                agent_runtime.AgentApproval.CONFIRM,
                lambda _: self._record_call(calls),
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
                lambda _: self._record_call(calls),
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
