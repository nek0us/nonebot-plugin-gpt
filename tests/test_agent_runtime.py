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
agent_readonly = importlib.import_module("nonebot_plugin_gpt.agent_readonly")


class _AgentService:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    async def turn(self, task, tools, *, state=None, tool_result=None, model="auto"):
        self.calls.append({"task": task, "tools": tools, "state": state, "tool_result": tool_result, "model": model})
        decision = self.decisions.pop(0)
        return AgentTurn(True, AgentState("conversation", f"message-{len(self.calls)}", model), decision)


class _FailedAgentService:
    def __init__(self, *, errors):
        self.errors = errors
        self.calls = []

    async def turn(self, task, tools, *, state=None, tool_result=None, model="auto"):
        self.calls.append({"task": task, "tools": tools, "state": state, "tool_result": tool_result, "model": model})
        return AgentTurn(
            False,
            state or AgentState(model=model),
            AgentDecision("error", error="upstream request failed"),
            errors=self.errors,
        )


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
    async def test_readonly_diagnostics_can_search_logs_and_source_without_writes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "logs"
            source = root / "source"
            logs.mkdir()
            source.mkdir()
            (logs / "bot.log").write_text("ERROR: token expired\n", encoding="utf-8")
            (source / "auth.py").write_text("raise TokenExpired()\n", encoding="utf-8")
            service = _AgentService([
                AgentDecision("tool_call", tool="搜索只读文本", arguments={
                    "根目录": "运行日志",
                    "文本": "token expired",
                }),
                AgentDecision("tool_call", tool="搜索只读文本", arguments={
                    "根目录": "核心源码",
                    "文本": "TokenExpired",
                }),
                AgentDecision("final", answer="令牌已经过期，认证刷新路径需要重新登录。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                agent_service=service,
                readonly_sources=agent_readonly.AgentReadonlyRoots([
                    {"name": "运行日志", "path": logs},
                    {"name": "核心源码", "path": source},
                ]),
                approval_mode=agent_runtime.AgentApprovalMode.FULL,
            )

            result = await runtime.execute("查日志并定位异常来源", operator_id="admin", scope_id="private:1")

            self.assertIn("令牌已经过期", result)
            self.assertEqual(len(service.calls), 3)
            self.assertIn("bot.log:1", service.calls[1]["tool_result"].output)
            self.assertIn("auth.py:1", service.calls[2]["tool_result"].output)

    async def test_readonly_text_analysis_is_available_for_any_configured_root(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "logs"
            logs.mkdir()
            (logs / "bot.log").write_text("INFO boot\nERROR expired\n", encoding="utf-8")
            service = _AgentService([
                AgentDecision("tool_call", tool="分析只读文本", arguments={
                    "根目录": "运行日志",
                    "文件": "bot.log",
                    "关键词": "ERROR",
                }),
                AgentDecision("final", answer="日志里有一条认证异常。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                agent_service=service,
                readonly_sources=agent_readonly.AgentReadonlyRoots([
                    {"name": "运行日志", "path": logs},
                ]),
                approval_mode=agent_runtime.AgentApprovalMode.FULL,
            )

            result = await runtime.execute("分析日志中的认证异常", operator_id="admin", scope_id="private:1")

            self.assertIn("认证异常", result)
            self.assertIn("总行数：2", service.calls[1]["tool_result"].output)

    async def test_readonly_path_locator_can_narrow_a_package_configuration_search(self):
        with TemporaryDirectory() as temporary:
            packages = Path(temporary) / "site-packages"
            package = packages / "nonebot_plugin_gpt"
            package.mkdir(parents=True)
            (package / "config.py").write_text("gpt_free_image = False\n", encoding="utf-8")
            service = _AgentService([
                AgentDecision("tool_call", tool="搜索只读文本", arguments={
                    "根目录": "已安装插件源码",
                    "文本": "nonebot_plugin_gpt",
                }),
                AgentDecision("tool_call", tool="搜索只读文本", arguments={
                    "根目录": "已安装插件源码",
                    "路径": "nonebot_plugin_gpt",
                    "文本": "gpt_free_image",
                }),
                AgentDecision("final", answer="识图开关是 gpt_free_image。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                agent_service=service,
                readonly_sources=agent_readonly.AgentReadonlyRoots([
                    {"name": "已安装插件源码", "path": packages},
                ]),
                approval_mode=agent_runtime.AgentApprovalMode.FULL,
            )

            result = await runtime.execute("查看插件识图配置", operator_id="admin", scope_id="private:1")

            self.assertIn("gpt_free_image", result)
            self.assertEqual(service.calls[1]["tool_result"].tool, "定位只读路径")
            self.assertIn("nonebot_plugin_gpt/", service.calls[1]["tool_result"].output)
            self.assertIn("config.py:1", service.calls[2]["tool_result"].output)

    async def test_readonly_root_routes_project_relative_paths_away_from_workspace(self):
        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "src"
            plugin = source / "plugins_my"
            workspace = project / "agent-workspace"
            plugin.mkdir(parents=True)
            workspace.mkdir()
            (plugin / "pool.py").write_text(
                "def eligible(member):\n    return member.active\n",
                encoding="utf-8",
            )
            service = _AgentService([
                AgentDecision("tool_call", tool="列出工作区文件", arguments={
                    "路径": "src/plugins_my",
                }),
                AgentDecision("final", answer="已定位到插件目录。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                agent_service=service,
                readonly_sources=agent_readonly.AgentReadonlyRoots([
                    {"name": "机器人自定义插件", "path": source},
                ]),
                workspace=workspace,
                approval_mode=agent_runtime.AgentApprovalMode.FULL,
            )

            result = await runtime.execute(
                "查看 src/plugins_my 的筛选规则",
                operator_id="admin",
                scope_id="private:1",
            )

            self.assertIn("已定位", result)
            prompt_task = service.calls[0]["task"]
            self.assertIn("【主机路径路由】", prompt_task)
            self.assertIn("`src/...`", prompt_task)
            self.assertIn("机器人自定义插件", prompt_task)
            self.assertEqual(service.calls[1]["tool_result"].tool, "列出只读目录")
            self.assertIn("plugins_my/", service.calls[1]["tool_result"].output)

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

    async def test_agent_model_turn_budget_stops_before_another_tool_round(self):
        async def inspect(_):
            return "first inspection completed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="inspect", arguments={}),
            AgentDecision("final", answer="should not be requested"),
        ], [agent_runtime.AgentTool(
            "inspect", "inspect local state", agent_runtime.AgentPermission.READ_LOCAL,
            agent_runtime.AgentApproval.AUTOMATIC, inspect,
        )], max_model_turns=1)

        text = await runtime.execute("inspect once", operator_id="admin", scope_id="private:1")

        self.assertIn("请求模型 1 次", text)
        self.assertEqual(len(runtime._agent_service.calls), 1)

    async def test_agent_task_timeout_stops_before_another_tool_round(self):
        now = [0.0]

        async def inspect(_):
            now[0] = 20.0
            return "inspection completed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="inspect", arguments={}),
            AgentDecision("final", answer="should not be requested"),
        ], [agent_runtime.AgentTool(
            "inspect", "inspect local state", agent_runtime.AgentPermission.READ_LOCAL,
            agent_runtime.AgentApproval.AUTOMATIC, inspect,
        )], task_timeout_seconds=5, clock=lambda: now[0])

        text = await runtime.execute("inspect once", operator_id="admin", scope_id="private:1")

        self.assertIn("超过 15 秒", text)
        self.assertEqual(len(runtime._agent_service.calls), 1)

    async def test_confirmation_wait_does_not_consume_the_agent_task_budget(self):
        now = [0.0]

        async def change(_):
            return "change completed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="change", arguments={}),
            AgentDecision("final", answer="completed"),
        ], [agent_runtime.AgentTool(
            "change", "perform a controlled change", agent_runtime.AgentPermission.WRITE_LOCAL,
            agent_runtime.AgentApproval.CONFIRM, change,
        )], task_timeout_seconds=15, confirmation_ttl_seconds=2000, clock=lambda: now[0])

        pending = await runtime.execute("make the change", operator_id="admin", scope_id="private:1")
        now[0] = 600.0
        completed = await runtime.execute("确认 plan", operator_id="admin", scope_id="private:1")

        self.assertIn("确认", pending)
        self.assertEqual(completed, "completed")
        self.assertEqual(len(runtime._agent_service.calls), 2)

    async def test_agent_rate_limit_error_uses_the_configured_safe_message(self):
        service = _FailedAgentService(errors=[{"kind": "conversation_rate_limited"}])
        runtime = agent_runtime.AgentRuntime(
            _Service(), [], agent_service=service,
            rate_limit_message="上游服务繁忙，请稍后再试。",
            error_message="智能体当前不可用。",
        )

        text = await runtime.execute("inspect the environment", operator_id="admin", scope_id="private:1")

        self.assertEqual(text, "上游服务繁忙，请稍后再试。")
        self.assertEqual(len(service.calls), 1)

    async def test_agent_model_error_uses_the_configured_safe_message(self):
        service = _FailedAgentService(errors=[])
        runtime = agent_runtime.AgentRuntime(
            _Service(), [], agent_service=service,
            error_message="智能体当前不可用。",
        )

        text = await runtime.execute("inspect the environment", operator_id="admin", scope_id="private:1")

        self.assertEqual(text, "智能体当前不可用。")
        self.assertNotIn("upstream request failed", text)

    async def test_agent_plan_error_uses_the_configured_safe_message(self):
        service = _FailedAgentService(errors=[])
        runtime = agent_runtime.AgentRuntime(
            _Service(), [], agent_service=service,
            error_message="智能体当前不可用。",
        )

        text = await runtime.execute("计划 检查环境", operator_id="admin", scope_id="private:1")

        self.assertEqual(text, "智能体计划未通过：智能体当前不可用。")
        self.assertNotIn("upstream request failed", text)

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

    async def test_confirmation_message_uses_configured_command_prefix(self):
        async def change(_):
            return "changed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="变更", arguments={}),
        ], [agent_runtime.AgentTool(
            "变更", "受控变更", agent_runtime.AgentPermission.WRITE_LOCAL,
            agent_runtime.AgentApproval.CONFIRM, change,
        )], command_prefix="猪咪 智能体")

        pending = await runtime.execute("执行变更", operator_id="admin", scope_id="private:1")

        self.assertIn("猪咪 智能体 确认 plan", pending)
        self.assertIn("猪咪 智能体 取消 plan", pending)

    async def test_confirmation_accepts_a_compact_control_command(self):
        called = []

        async def change(_):
            called.append(True)
            return "changed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="变更", arguments={}),
            AgentDecision("final", answer="完成。"),
        ], [agent_runtime.AgentTool(
            "变更", "受控变更", agent_runtime.AgentPermission.WRITE_LOCAL,
            agent_runtime.AgentApproval.CONFIRM, change,
        )])

        await runtime.execute("请执行受控变更", operator_id="admin", scope_id="private:1")
        completed = await runtime.execute("确认plan", operator_id="admin", scope_id="private:1")

        self.assertEqual(called, [True])
        self.assertIn("完成", completed)

    async def test_delegate_mode_runs_workspace_writes_without_confirmation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            service = _AgentService([
                AgentDecision("tool_call", tool="写入工作区文件", arguments={
                    "路径": "hello.txt",
                    "内容": "hello from agent",
                }),
                AgentDecision("final", answer="文件已创建。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                workspace=root,
                approval_mode=agent_runtime.AgentApprovalMode.DELEGATE,
                agent_service=service,
            )

            completed = await runtime.execute("创建 hello.txt", operator_id="admin", scope_id="private:1")

            self.assertEqual((root / "hello.txt").read_text(encoding="utf-8"), "hello from agent")
            self.assertIn("文件已创建", completed)

    async def test_delegate_mode_keeps_non_delegable_change_pending(self):
        async def change(_):
            return "changed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="变更", arguments={}),
        ], [agent_runtime.AgentTool(
            "变更", "受控变更", agent_runtime.AgentPermission.WRITE_LOCAL,
            agent_runtime.AgentApproval.CONFIRM, change,
        )], approval_mode=agent_runtime.AgentApprovalMode.DELEGATE)

        pending = await runtime.execute("执行变更", operator_id="admin", scope_id="private:1")

        self.assertIn("确认 plan", pending)

    async def test_full_mode_runs_registered_change_without_confirmation(self):
        called = []

        async def change(_):
            called.append(True)
            return "changed"

        runtime = _runtime([
            AgentDecision("tool_call", tool="变更", arguments={}),
            AgentDecision("final", answer="完成。"),
        ], [agent_runtime.AgentTool(
            "变更", "受控变更", agent_runtime.AgentPermission.WRITE_LOCAL,
            agent_runtime.AgentApproval.CONFIRM, change,
        )], approval_mode=agent_runtime.AgentApprovalMode.FULL)

        completed = await runtime.execute("执行变更", operator_id="admin", scope_id="private:1")

        self.assertEqual(called, [True])
        self.assertIn("完成", completed)

    async def test_workspace_image_is_attached_after_model_finishes(self):
        class _Renderer:
            async def render(self, source, output):
                self.source = source
                self.output = output
                return output, b"\x89PNG\r\n\x1a\nrendered"

            def validate(self, source, output):
                if source != "page.html" or output != "screenshots/page.png":
                    raise ValueError("unexpected path")

        rendered = []

        async def final_renderer(run, answer):
            rendered.append((answer, run.artifacts))
            return "任务完成"

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "page.html").write_text("<main>hello</main>", encoding="utf-8")
            service = _AgentService([
                AgentDecision("tool_call", tool="渲染工作区网页", arguments={
                    "HTML文件": "page.html",
                    "截图文件": "screenshots/page.png",
                }),
                AgentDecision("final", answer="网页已完成。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                workspace=root,
                workspace_web_renderer=_Renderer(),
                agent_service=service,
                final_renderer=final_renderer,
                token_factory=iter(("confirm", "next")).__next__,
            )

            pending = await runtime.execute("制作网页截图", operator_id="admin", scope_id="private:1")
            completed = await runtime.execute("确认 confirm", operator_id="admin", scope_id="private:1")

        self.assertIn("确认 confirm", pending)
        self.assertEqual(completed, "任务完成")
        self.assertEqual(rendered[0][0], "网页已完成。")
        self.assertEqual(rendered[0][1][0].path, "screenshots/page.png")
        self.assertEqual(rendered[0][1][0].content, b"\x89PNG\r\n\x1a\nrendered")

    async def test_workspace_file_is_attached_as_a_generic_artifact(self):
        rendered = []

        async def final_renderer(run, answer):
            rendered.append((answer, run.artifacts))
            return "任务完成"

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "report.txt").write_text("agent report", encoding="utf-8")
            service = _AgentService([
                AgentDecision("tool_call", tool="回传工作区文件", arguments={"文件": "report.txt"}),
                AgentDecision("final", answer="报告已生成。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                workspace=root,
                agent_service=service,
                final_renderer=final_renderer,
                token_factory=iter(("confirm", "next")).__next__,
            )

            pending = await runtime.execute("把报告发给我", operator_id="admin", scope_id="private:1")
            completed = await runtime.execute("确认 confirm", operator_id="admin", scope_id="private:1")

        self.assertIn("回传工作目录文件 report.txt", pending)
        self.assertEqual(completed, "任务完成")
        self.assertEqual(rendered[0][1][0].path, "report.txt")
        self.assertEqual(rendered[0][1][0].media_type, "text/plain")
        self.assertEqual(rendered[0][1][0].content, b"agent report")

    async def test_delegate_mode_keeps_workspace_deletion_pending(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "temporary.txt").write_text("remove me", encoding="utf-8")
            service = _AgentService([
                AgentDecision("tool_call", tool="删除工作区文件", arguments={"路径": "temporary.txt"}),
                AgentDecision("final", answer="清理完成。"),
            ])
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                workspace=root,
                approval_mode=agent_runtime.AgentApprovalMode.DELEGATE,
                agent_service=service,
                token_factory=iter(("confirm", "next")).__next__,
            )

            pending = await runtime.execute("删除临时文件", operator_id="admin", scope_id="private:1")
            self.assertTrue((root / "temporary.txt").exists())
            completed = await runtime.execute("确认 confirm", operator_id="admin", scope_id="private:1")

        self.assertIn("不可恢复", pending)
        self.assertIn("清理完成", completed)
        self.assertFalse((root / "temporary.txt").exists())

    async def test_workspace_tool_catalog_exposes_project_operations_to_the_model(self):
        service = _AgentService([AgentDecision("final", answer="可以开始。")])
        with TemporaryDirectory() as temporary:
            runtime = agent_runtime.create_agent_runtime(
                _Service(),
                workspace=Path(temporary),
                agent_service=service,
            )
            await runtime.execute("帮我整理一个小项目", operator_id="admin", scope_id="private:1")

        names = {tool.name for tool in service.calls[0]["tools"]}
        self.assertTrue({
            "查看工作区路径", "创建工作区目录", "搜索工作区文本", "追加工作区文件",
            "替换工作区文本", "复制工作区文件", "移动工作区文件", "删除工作区文件",
            "回传工作区文件",
        }.issubset(names))

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

    async def test_mentioned_target_hides_personal_reminder_tool_from_model(self):
        service = _AgentService([
            AgentDecision("final", answer="等待安排。"),
        ])
        runtime = agent_runtime.create_agent_runtime(
            _Service(),
            agent_service=service,
            schedule_reminder=lambda *_: None,
            schedule_target_reminder=lambda *_: None,
        )

        await runtime.execute(
            "30 秒后提醒 @成员 吃饭",
            operator_id="admin",
            scope_id="onebot.v11:group:1",
            mentioned_user_ids=("member-2",),
        )

        tool_names = {tool.name for tool in service.calls[0]["tools"]}
        self.assertNotIn("安排提醒", tool_names)
        self.assertIn("安排指定提醒", tool_names)

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

    async def test_extra_tool_provider_is_registered_and_keeps_confirmation_boundary(self):
        calls = []

        async def inspect(_):
            calls.append(True)
            return "扩展工具结果"

        def provider(access):
            self.assertIs(access, agent_runtime.AgentAccess.SUPERUSER)
            return [agent_runtime.AgentTool(
                "扩展诊断", "由附加插件提供的受控诊断", agent_runtime.AgentPermission.READ_LOCAL,
                agent_runtime.AgentApproval.CONFIRM, inspect,
            )]

        runtime = _runtime([
            AgentDecision("tool_call", tool="扩展诊断", arguments={}),
            AgentDecision("final", answer="诊断完成"),
        ], [])
        provided_runtime = agent_runtime.create_agent_runtime(
            _Service(),
            agent_service=runtime._agent_service,
            tool_providers=(provider,),
            token_factory=iter(("confirm", "next")).__next__,
        )

        pending = await provided_runtime.execute("执行扩展诊断", operator_id="admin", scope_id="private:1")
        completed = await provided_runtime.execute("确认 confirm", operator_id="admin", scope_id="private:1")

        self.assertIn("本机只读", pending)
        self.assertEqual(calls, [True])
        self.assertIn("诊断完成", completed)
