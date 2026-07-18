import importlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ChatGPTWeb import AgentDecision, AgentState, AgentTurn


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
agent_runtime = importlib.import_module("nonebot_plugin_gpt.agent_runtime")


class _AgentService:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    async def turn(self, task, tools, *, state=None, tool_result=None, model="auto"):
        self.calls.append({"task": task, "tools": tools, "state": state, "tool_result": tool_result, "model": model})
        decision = self.decisions.pop(0)
        return AgentTurn(True, AgentState("conversation", f"message-{len(self.calls)}", model), decision)


class _Service:
    async def get_account_status(self):
        return {"accounts": []}

    async def get_model_catalog(self, fetch_remote=False):
        return {"local": {"free": {"auto": "auto"}, "plus": {}}}


def _runtime(decisions, tools, **kwargs):
    return agent_runtime.AgentRuntime(
        _Service(),
        tools,
        agent_service=_AgentService(decisions),
        token_factory=kwargs.pop("token_factory", iter(("plan", "confirm", "next")).__next__),
        **kwargs,
    )


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_renderer_can_present_an_agent_result_in_the_current_persona(self):
        rendered = []

        async def render(run, answer):
            rendered.append((run.task, answer))
            return "（轻轻点头）一分钟后提醒你喝水咩。"

        runtime = _runtime([
            AgentDecision("final", answer="提醒已安排。"),
        ], [], final_renderer=render)

        text = await runtime.execute("一分钟后提醒我喝水", operator_id="admin", scope_id="group:1")

        self.assertEqual(text, "（轻轻点头）一分钟后提醒你喝水咩。")
        self.assertEqual(rendered, [("一分钟后提醒我喝水", "提醒已安排。")])

    async def test_agent_runs_multiple_model_tool_turns_and_returns_final_answer(self):
        calls = []

        async def inspect(arguments):
            calls.append(arguments)
            return "环境正常"

        runtime = _runtime([
            AgentDecision("tool_call", tool="环境", arguments={}, summary="先检查环境"),
            AgentDecision("final", answer="环境正常，可以继续。"),
        ], [agent_runtime.AgentTool(
            "环境", "检查本机环境", agent_runtime.AgentPermission.READ_LOCAL,
            agent_runtime.AgentApproval.AUTOMATIC, inspect,
        )])

        text = await runtime.execute("执行 检查环境", operator_id="admin", scope_id="group:1")

        self.assertEqual(calls, [{}])
        self.assertIn("环境正常，可以继续", text)
        self.assertEqual(len(runtime._agent_service.calls), 2)
        self.assertEqual(runtime._agent_service.calls[1]["tool_result"].tool, "环境")

    async def test_write_tool_pauses_for_bound_confirmation_then_continues(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = _runtime([
                AgentDecision("tool_call", tool="写入工作区文件", arguments={"路径": "hello.txt", "内容": "hello from agent"}),
                AgentDecision("final", answer="文件已创建。"),
            ], [])
            workspace_runtime = agent_runtime.create_agent_runtime(
                _Service(),
                workspace=root,
                agent_service=runtime._agent_service,
                token_factory=iter(("confirm", "next")).__next__,
            )

            pending = await workspace_runtime.execute("执行 创建 hello.txt", operator_id="admin", scope_id="private:1")
            completed = await workspace_runtime.execute("确认 confirm", operator_id="admin", scope_id="private:1")

            self.assertIn("本机写入", pending)
            self.assertEqual((root / "hello.txt").read_text(encoding="utf-8"), "hello from agent")
            self.assertIn("文件已创建", completed)

    async def test_plan_is_real_first_decision_and_executes_only_after_its_token(self):
        calls = []

        async def inspect(_):
            calls.append("called")
            return "done"

        runtime = _runtime([
            AgentDecision("tool_call", tool="环境", arguments={}, summary="检查环境"),
            AgentDecision("final", answer="完成"),
        ], [agent_runtime.AgentTool(
            "环境", "检查环境", agent_runtime.AgentPermission.READ_LOCAL,
            agent_runtime.AgentApproval.AUTOMATIC, inspect,
        )])

        planned = await runtime.execute("计划 检查环境", operator_id="admin", scope_id="group:1")
        executed = await runtime.execute("执行 plan", operator_id="admin", scope_id="group:1")

        self.assertIn("未执行", planned)
        self.assertEqual(calls, ["called"])
        self.assertIn("完成", executed)

    async def test_confirmation_is_bound_to_original_operator_and_scope(self):
        async def change(_):
            return "changed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="变更", arguments={}),
            AgentDecision("final", answer="完成"),
        ], [agent_runtime.AgentTool(
            "变更", "受控变更", agent_runtime.AgentPermission.WRITE_LOCAL,
            agent_runtime.AgentApproval.CONFIRM, change,
        )])

        await runtime.execute("执行 进行变更", operator_id="admin", scope_id="group:1")
        rejected = await runtime.execute("确认 plan", operator_id="other", scope_id="group:1")
        completed = await runtime.execute("确认 plan", operator_id="admin", scope_id="group:1")

        self.assertIn("原操作者", rejected)
        self.assertIn("完成", completed)

    async def test_invalid_model_tool_arguments_are_rejected_without_execution(self):
        calls = []

        async def handler(_):
            calls.append("called")
            return "bad"

        runtime = _runtime([
            AgentDecision("tool_call", tool="环境", arguments={"unexpected": "x"}),
        ], [agent_runtime.AgentTool(
            "环境", "检查环境", agent_runtime.AgentPermission.READ_LOCAL,
            agent_runtime.AgentApproval.AUTOMATIC, handler,
        )])

        text = await runtime.execute("执行 检查", operator_id="admin", scope_id="private:1")

        self.assertIn("参数未通过本地校验", text)
        self.assertEqual(calls, [])

    async def test_read_authorization_can_skip_repeated_confirmation(self):
        calls = []

        async def read(_):
            calls.append("read")
            return "content"

        runtime = _runtime([], [agent_runtime.AgentTool(
            "读取", "读取", agent_runtime.AgentPermission.READ_LOCAL,
            agent_runtime.AgentApproval.CONFIRM, read,
        )])

        pending = await runtime.execute("授权 本机只读", operator_id="admin", scope_id="private:1")
        granted = await runtime.execute("确认 plan", operator_id="admin", scope_id="private:1")
        direct = await runtime.execute("读取", operator_id="admin", scope_id="private:1")

        self.assertIn("确认", pending)
        self.assertIn("已授予", granted)
        self.assertTrue(direct.startswith("content"))
        self.assertEqual(calls, ["read"])

    async def test_natural_language_task_starts_model_loop_without_execute_prefix(self):
        called = []

        async def inspect(_):
            called.append(True)
            return "环境正常"

        runtime = _runtime([
            AgentDecision("tool_call", tool="环境", arguments={}),
            AgentDecision("final", answer="（轻轻点头）环境已经检查好了咩。"),
        ], [agent_runtime.AgentTool(
            "环境", "检查环境", agent_runtime.AgentPermission.READ_LOCAL,
            agent_runtime.AgentApproval.AUTOMATIC, inspect,
        )])

        text = await runtime.execute("检查一下当前环境", operator_id="admin", scope_id="private:1")

        self.assertEqual(called, [True])
        self.assertEqual(text, "（轻轻点头）环境已经检查好了咩。")

    async def test_scheduled_event_tool_receives_original_delivery_context(self):
        scheduled = []

        async def schedule(run, delay_seconds, content):
            scheduled.append((run.conversation_key, run.delivery_target, run.delivery_user_id, delay_seconds, content))
            return "提醒已安排"

        runtime = _runtime([
            AgentDecision("tool_call", tool="安排提醒", arguments={"延迟秒数": "600", "内容": "喝水"}),
            AgentDecision("final", answer="（摇摇尾巴）十分钟后会提醒你喝水咩。"),
        ], [])
        scheduled_runtime = agent_runtime.create_agent_runtime(
            _Service(),
            agent_service=runtime._agent_service,
            schedule_reminder=schedule,
            token_factory=iter(("next",)).__next__,
        )
        key = agent_runtime.ConversationKey("onebot.v11:group:1", "")

        text = await scheduled_runtime.execute(
            "十分钟后提醒我喝水",
            operator_id="admin",
            scope_id="onebot.v11:group:1",
            conversation_key=key,
            delivery_target={"adapter": "OneBot V11", "id": "1"},
            delivery_user_id="admin",
        )

        self.assertEqual(text, "（摇摇尾巴）十分钟后会提醒你喝水咩。")
        self.assertEqual(scheduled, [(key, {"adapter": "OneBot V11", "id": "1"}, "admin", 600, "喝水")])

    async def test_superuser_can_schedule_a_reminder_for_an_actually_mentioned_member_after_confirmation(self):
        scheduled = []

        async def schedule_target(run, delay_seconds, content, target_user_id):
            scheduled.append((run.operator_id, target_user_id, delay_seconds, content))
            return "已为指定成员安排提醒。"

        runtime = _runtime([
            AgentDecision("tool_call", tool="安排指定提醒", arguments={
                "延迟秒数": "120",
                "对象ID": "member-2",
                "内容": "吃饭啦",
            }),
            AgentDecision("final", answer="提醒已经安排好啦。"),
        ], [])
        target_runtime = agent_runtime.create_agent_runtime(
            _Service(),
            agent_service=runtime._agent_service,
            schedule_target_reminder=schedule_target,
            token_factory=iter(("confirm", "next")).__next__,
        )
        key = agent_runtime.ConversationKey("onebot.v11:group:1", "")

        pending = await target_runtime.execute(
            "两分钟后提醒 @成员 吃饭",
            operator_id="admin",
            scope_id="onebot.v11:group:1",
            conversation_key=key,
            delivery_target={"adapter": "OneBot V11", "id": "1"},
            delivery_user_id="admin",
            mentioned_user_ids=("member-2",),
        )
        completed = await target_runtime.execute(
            "确认 confirm",
            operator_id="admin",
            scope_id="onebot.v11:group:1",
        )

        self.assertIn("确认 confirm", pending)
        self.assertEqual(scheduled, [("admin", "member-2", 120, "吃饭啦")])
        self.assertEqual(completed, "提醒已经安排好啦。")

    async def test_target_reminder_rejects_a_user_not_mentioned_in_the_source_message(self):
        scheduled = []

        async def schedule_target(*_):
            scheduled.append(True)
            return "unexpected"

        runtime = _runtime([
            AgentDecision("tool_call", tool="安排指定提醒", arguments={
                "延迟秒数": "120",
                "对象ID": "not-mentioned",
                "内容": "吃饭啦",
            }),
        ], [])
        target_runtime = agent_runtime.create_agent_runtime(
            _Service(),
            agent_service=runtime._agent_service,
            schedule_target_reminder=schedule_target,
        )

        text = await target_runtime.execute(
            "两分钟后提醒某人吃饭",
            operator_id="admin",
            scope_id="onebot.v11:group:1",
            mentioned_user_ids=("member-2",),
        )

        self.assertIn("实际提及", text)
        self.assertEqual(scheduled, [])
        self.assertEqual(target_runtime._pending, {})

    async def test_member_runtime_only_exposes_personal_reminder_tools(self):
        scheduled = []

        async def schedule(run, delay_seconds, content):
            scheduled.append((run.access, run.operator_id, delay_seconds, content))
            return "提醒已安排"

        async def operate(run, operation, identifier):
            return f"{operation}:{identifier}:{run.operator_id}"

        runtime = _runtime([
            AgentDecision("tool_call", tool="安排提醒", arguments={"延迟秒数": "600", "内容": "喝水"}),
            AgentDecision("final", answer="（轻轻点头）十分钟后提醒你咩。"),
        ], [])
        member_runtime = agent_runtime.create_agent_runtime(
            _Service(),
            agent_service=runtime._agent_service,
            schedule_reminder=schedule,
            reminder_operation=operate,
            access=agent_runtime.AgentAccess.MEMBER,
        )
        key = agent_runtime.ConversationKey("onebot.v11:group:1", "")

        text = await member_runtime.execute(
            "十分钟后提醒我喝水",
            operator_id="member",
            scope_id="onebot.v11:group:1",
            conversation_key=key,
            delivery_target={"adapter": "OneBot V11", "id": "1"},
            delivery_user_id="member",
        )

        self.assertEqual(set(member_runtime._tools), {"安排提醒", "查看我的提醒", "取消我的提醒"})
        self.assertEqual(scheduled, [(agent_runtime.AgentAccess.MEMBER, "member", 600, "喝水")])
        self.assertEqual(text, "（轻轻点头）十分钟后提醒你咩。")
