"""由核心 Agent 协议驱动的 NoneBot 受控工具宿主。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from secrets import token_urlsafe
from time import monotonic, perf_counter
from typing import Any

from ChatGPTWeb import AgentDecision, AgentService, AgentState, AgentTool as CoreAgentTool, AgentToolResult, AgentTurn, ChatService
from nonebot.log import logger

from .agent_audit import AgentAuditLog
from .agent_commands import CommandRunner, CommandValidationError
from .agent_filesystem import AgentFilesystemScanner
from .agent_skills import AgentSkillError, DeclarativeCommandSkill
from .agent_workspace import AgentWorkspace, WorkspaceError
from .conversation import ConversationKey
from .environment_diagnostics import collect_environment_diagnostics, format_environment_diagnostics
from .managed_services import ManagedServiceRegistry
from .management_views import format_account_status


AgentActionHandler = Callable[[dict[str, str]], Awaitable[str]]
AgentTurnHandler = Callable[..., Awaitable[AgentTurn]]
AgentRunActionHandler = Callable[[dict[str, str], "AgentRun"], Awaitable[str]]
AgentRunArgumentValidator = Callable[[dict[str, str], "AgentRun"], str]
ReminderScheduleHandler = Callable[["AgentRun", int, str], Awaitable[str]]
TargetReminderScheduleHandler = Callable[["AgentRun", int, str, str], Awaitable[str]]
ReminderOperationHandler = Callable[["AgentRun", str, str], Awaitable[str]]
AgentFinalRenderer = Callable[["AgentRun", str], Awaitable[str]]


class AgentPermission(str, Enum):
    """工具实际能力类别；模型只能看到说明，不能决定权限。"""

    READ_LOCAL = "read_local"
    READ_NETWORK = "read_network"
    WRITE_LOCAL = "write_local"
    PROCESS_CONTROL = "process_control"
    MESSAGE_SEND = "message_send"
    DESTRUCTIVE = "destructive"


class AgentApproval(str, Enum):
    """单个工具的审批策略。"""

    AUTOMATIC = "automatic"
    CONFIRM = "confirm"


class AgentAccess(str, Enum):
    """智能体入口可见的工具档位。"""

    MEMBER = "member"
    SUPERUSER = "superuser"


_PERMISSION_NAMES = {
    AgentPermission.READ_LOCAL: "本机只读",
    AgentPermission.READ_NETWORK: "网络读取",
    AgentPermission.WRITE_LOCAL: "本机写入",
    AgentPermission.PROCESS_CONTROL: "进程控制",
    AgentPermission.MESSAGE_SEND: "消息投递",
    AgentPermission.DESTRUCTIVE: "高风险变更",
}
_GRANTABLE_PERMISSIONS = {AgentPermission.READ_LOCAL}


@dataclass(frozen=True)
class AgentToolParameter:
    """由插件本地校验的字符串参数。"""

    name: str
    description: str
    required: bool = True
    choices: tuple[str, ...] = ()
    sensitive: bool = False


@dataclass(frozen=True)
class AgentTool:
    """插件显式注册的本地工具，不接受模型临时扩展。"""

    name: str
    description: str
    permission: AgentPermission
    approval: AgentApproval
    handler: AgentActionHandler
    parameters: tuple[AgentToolParameter, ...] = ()
    describe_action: Callable[[dict[str, str]], str] | None = None
    run_handler: AgentRunActionHandler | None = None
    argument_validator: Callable[[dict[str, str]], str] | None = None
    run_argument_validator: AgentRunArgumentValidator | None = None
    minimum_access: AgentAccess = AgentAccess.SUPERUSER

    def core_definition(self) -> CoreAgentTool:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in self.parameters:
            rule: dict[str, Any] = {
                "type": "string",
                "description": parameter.description,
                "maxLength": 8192,
            }
            if parameter.choices:
                rule["enum"] = list(parameter.choices)
            properties[parameter.name] = rule
            if parameter.required:
                required.append(parameter.name)
        return CoreAgentTool(
            self.name,
            self.description,
            {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        )


# 外部插件可在加载阶段注册受控工具提供者。提供者只能交回本模块的
# AgentTool；权限、参数校验与确认仍由 AgentRuntime 统一执行。
AgentToolProvider = Callable[["AgentAccess"], Iterable[AgentTool]]
_TOOL_PROVIDERS: list[AgentToolProvider] = []


def register_agent_tool_provider(provider: AgentToolProvider) -> AgentToolProvider:
    """注册一个附加工具提供者，并返回它以便用作装饰器。"""
    if provider not in _TOOL_PROVIDERS:
        _TOOL_PROVIDERS.append(provider)
    return provider


@dataclass
class AgentRun:
    """绑定原操作者与原聊天范围的一次多轮模型任务。"""

    task: str
    state: AgentState
    operator_id: str
    scope_id: str
    steps: int = 0
    model: str = "auto"
    conversation_key: ConversationKey | None = None
    delivery_target: dict[str, Any] | None = None
    delivery_user_id: str = ""
    mentioned_user_ids: tuple[str, ...] = ()
    agent_context: str = ""
    access: AgentAccess = AgentAccess.SUPERUSER


@dataclass
class PendingAgentAction:
    """等待明确确认后才执行并继续模型循环的动作。"""

    token: str
    tool: AgentTool
    arguments: dict[str, str]
    run: AgentRun | None
    operator_id: str
    scope_id: str
    expires_at: float
    direct: bool = False


@dataclass
class PlannedAgentRun:
    """只规划首步、尚未开始执行的真实 Agent 回合。"""

    token: str
    run: AgentRun
    decision: AgentDecision
    operator_id: str
    scope_id: str
    expires_at: float


class AgentRuntime:
    """把核心模型决策与本地工具执行、审批和审计连接起来。"""

    def __init__(
        self,
        service: ChatService,
        tools: list[AgentTool],
        *,
        confirmation_ttl_seconds: int = 60,
        session_approval_ttl_seconds: int = 1800,
        plan_ttl_seconds: int = 300,
        max_steps: int = 8,
        model: str = "auto",
        audit_log: AgentAuditLog | None = None,
        clock: Callable[[], float] = monotonic,
        token_factory: Callable[[], str] = lambda: token_urlsafe(6),
        agent_service: AgentService | None = None,
        agent_turn: AgentTurnHandler | None = None,
        schedule_reminder: ReminderScheduleHandler | None = None,
        schedule_target_reminder: TargetReminderScheduleHandler | None = None,
        reminder_operation: ReminderOperationHandler | None = None,
        final_renderer: AgentFinalRenderer | None = None,
        access: AgentAccess = AgentAccess.SUPERUSER,
    ):
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("智能体工具名称不能重复")
        self._agent_service = agent_service or AgentService(service)
        self._agent_turn = agent_turn
        self._schedule_target_reminder = schedule_target_reminder
        self._final_renderer = final_renderer
        self._access = access
        self._confirmation_ttl_seconds = confirmation_ttl_seconds
        self._session_approval_ttl_seconds = session_approval_ttl_seconds
        self._plan_ttl_seconds = plan_ttl_seconds
        self._max_steps = max(1, min(max_steps, 20))
        self._model = model or "auto"
        self._clock = clock
        self._token_factory = token_factory
        self._audit = audit_log or AgentAuditLog()
        self._pending: dict[str, PendingAgentAction] = {}
        self._plans: dict[str, PlannedAgentRun] = {}
        self._approvals: dict[tuple[str, str, AgentPermission], float] = {}

    def help_text(self) -> str:
        heading = "智能体工具（成员安全模式）" if self._access is AgentAccess.MEMBER else "智能体工具（超级用户）"
        lines = [heading]
        for tool in self._tools.values():
            approval = "需要确认" if tool.approval is AgentApproval.CONFIRM else "自动执行"
            lines.append(f"- {tool.name}：{tool.description}（{_PERMISSION_NAMES[tool.permission]}，{approval}）")
        lines.extend([
            "",
            "执行任务：智能体 <任务>。模型会按需多轮调用已注册工具，自动允许的步骤会继续执行。",
            "只看首步计划：智能体 计划 <任务>；再用 智能体 执行 <计划编号> 开始。",
        ])
        if self._access is AgentAccess.SUPERUSER:
            lines.extend([
                "高风险步骤会返回确认编号；仅原超级用户可在原聊天范围使用 智能体 确认 <编号> 或 智能体 取消 <编号>。",
                "可用：智能体 审计 [数量] / 智能体 授权 本机只读 / 智能体 授权列表 / 智能体 撤销授权。",
            ])
        return "\n".join(lines)

    def _core_tools(self, run: AgentRun | None = None) -> list[CoreAgentTool]:
        tools = self._tools.values()
        if run is not None and run.mentioned_user_ids and "安排指定提醒" in self._tools:
            # 有真实 @ 目标时，不能让模型误用“提醒自己”的工具。
            tools = (tool for tool in tools if tool.name != "安排提醒")
        return [tool.core_definition() for tool in tools]

    def _discard_expired(self) -> None:
        now = self._clock()
        self._pending = {token: item for token, item in self._pending.items() if item.expires_at > now}
        self._plans = {token: item for token, item in self._plans.items() if item.expires_at > now}
        self._approvals = {key: expires_at for key, expires_at in self._approvals.items() if expires_at > now}

    def _new_token(self) -> str:
        token = self._token_factory()
        while token in self._pending or token in self._plans:
            token = self._token_factory()
        return token

    @staticmethod
    def _validate_arguments(tool: AgentTool, arguments: dict[str, Any]) -> tuple[dict[str, str], str]:
        expected = {item.name: item for item in tool.parameters}
        unknown = set(arguments).difference(expected)
        if unknown:
            return {}, f"包含未声明参数：{'、'.join(sorted(unknown))}"
        normalized: dict[str, str] = {}
        for name, parameter in expected.items():
            value = arguments.get(name)
            if value is None:
                if parameter.required:
                    return {}, f"缺少必填参数：{name}"
                continue
            if not isinstance(value, str):
                return {}, f"参数 {name} 必须是文本"
            if parameter.choices and value not in parameter.choices:
                return {}, f"参数 {name} 仅允许：{'、'.join(parameter.choices)}"
            normalized[name] = value
        return normalized, ""

    def _has_session_approval(self, permission: AgentPermission, operator_id: str, scope_id: str) -> bool:
        return self._approvals.get((operator_id, scope_id, permission), 0) > self._clock()

    def _format_arguments(self, tool: AgentTool, arguments: dict[str, str]) -> str:
        if not arguments:
            return "无"
        parameters = {parameter.name: parameter for parameter in tool.parameters}
        return "；".join(
            f"{name}：{'已提供' if parameters[name].sensitive else value}"
            for name, value in arguments.items()
        )

    def _pending_message(self, action: PendingAgentAction) -> str:
        description = action.tool.describe_action(action.arguments) if action.tool.describe_action else action.tool.description
        return "\n".join([
            f"智能体准备执行：{description}",
            f"权限：{_PERMISSION_NAMES[action.tool.permission]}",
            f"参数：{self._format_arguments(action.tool, action.arguments)}",
            f"请在 {self._confirmation_ttl_seconds} 秒内发送“智能体 确认 {action.token}”，或发送“智能体 取消 {action.token}”。",
        ])

    def _queue_confirmation(
        self,
        tool: AgentTool,
        arguments: dict[str, str],
        run: AgentRun | None,
        operator_id: str,
        scope_id: str,
        *,
        direct: bool = False,
    ) -> str:
        self._discard_expired()
        token = self._new_token()
        action = PendingAgentAction(
            token=token,
            tool=tool,
            arguments=arguments,
            run=run,
            operator_id=operator_id,
            scope_id=scope_id,
            expires_at=self._clock() + self._confirmation_ttl_seconds,
            direct=direct,
        )
        self._pending[token] = action
        self._audit.record("确认已创建", tool.name, _PERMISSION_NAMES[tool.permission])
        return self._pending_message(action)

    async def _call_tool(
        self,
        tool: AgentTool,
        arguments: dict[str, str],
        run: AgentRun | None = None,
    ) -> AgentToolResult:
        started_at = perf_counter()
        try:
            if tool.run_handler is not None:
                if run is None:
                    return AgentToolResult(tool.name, "该工具只能在智能体任务中调用。", ok=False)
                output = await tool.run_handler(arguments, run)
            else:
                output = await tool.handler(arguments)
        except Exception:
            logger.exception(f"智能体工具“{tool.name}”执行异常")
            self._audit.record("工具执行失败", tool.name, _PERMISSION_NAMES[tool.permission])
            return AgentToolResult(tool.name, "工具执行失败，未返回内部错误细节。", ok=False)
        elapsed_ms = max(0, round((perf_counter() - started_at) * 1000))
        self._audit.record("工具执行完成", tool.name, _PERMISSION_NAMES[tool.permission])
        return AgentToolResult(tool.name, str(output)[:12000] + f"\n\n[工具耗时：{elapsed_ms} 毫秒]", ok=True)

    async def _request_turn(
        self,
        task: str,
        *,
        run: AgentRun | None = None,
        state: AgentState | None = None,
        tool_result: AgentToolResult | None = None,
    ) -> AgentTurn:
        if self._agent_turn is not None and run is not None and run.conversation_key is not None:
            return await self._agent_turn(
                key=run.conversation_key,
                task=task,
                tools=self._core_tools(run),
                state=state,
                tool_result=tool_result,
                model=run.model,
            )
        return await self._agent_service.turn(
            task,
            self._core_tools(run),
            state=state,
            tool_result=tool_result,
            model=run.model if run is not None else self._model,
        )

    async def _continue_after_result(self, run: AgentRun, result: AgentToolResult) -> str:
        turn = await self._request_turn("", run=run, state=run.state, tool_result=result)
        run.state = turn.state
        return await self._handle_turn(turn, run)

    async def _handle_turn(self, turn: AgentTurn, run: AgentRun) -> str:
        if not turn.ok or turn.decision.kind == "error":
            self._audit.record("模型决策失败", "智能体模型")
            return f"智能体未能继续执行：{turn.decision.error or '模型请求失败'}"
        if turn.decision.kind == "final":
            self._audit.record("任务已完成", "智能体模型")
            if self._final_renderer is not None:
                try:
                    return await self._final_renderer(run, turn.decision.answer)
                except Exception:
                    logger.exception("智能体最终答复人设化失败，回退到控制会话答复")
            return turn.decision.answer
        if run.steps >= self._max_steps:
            self._audit.record("任务达到步数上限", "智能体模型")
            return f"智能体已执行 {self._max_steps} 步，为避免失控循环已停止。请根据当前结果重新提出任务。"
        tool = self._tools.get(turn.decision.tool)
        if tool is None:
            self._audit.record("模型请求未注册工具", turn.decision.tool)
            return "智能体请求了不可用工具，已拒绝执行。"
        arguments, error = self._validate_arguments(tool, turn.decision.arguments)
        if error:
            self._audit.record("工具参数被拒绝", tool.name, _PERMISSION_NAMES[tool.permission])
            return f"智能体工具参数未通过本地校验：{error}"
        if tool.argument_validator is not None and (error := tool.argument_validator(arguments)):
            self._audit.record("工具参数被拒绝", tool.name, _PERMISSION_NAMES[tool.permission])
            return f"智能体工具参数未通过本地校验：{error}"
        if tool.run_argument_validator is not None and (error := tool.run_argument_validator(arguments, run)):
            self._audit.record("工具参数被拒绝", tool.name, _PERMISSION_NAMES[tool.permission])
            return f"智能体工具参数未通过本地校验：{error}"
        run.steps += 1
        if tool.approval is AgentApproval.CONFIRM and not self._has_session_approval(tool.permission, run.operator_id, run.scope_id):
            return self._queue_confirmation(tool, arguments, run, run.operator_id, run.scope_id)
        return await self._continue_after_result(run, await self._call_tool(tool, arguments, run))

    async def _start(
        self,
        task: str,
        operator_id: str,
        scope_id: str,
        *,
        plan_only: bool,
        conversation_key: ConversationKey | None = None,
        delivery_target: dict[str, Any] | None = None,
        delivery_user_id: str = "",
        mentioned_user_ids: tuple[str, ...] = (),
        agent_context: str = "",
    ) -> str:
        run = AgentRun(
            task=task,
            state=AgentState(model=self._model),
            operator_id=operator_id,
            scope_id=scope_id,
            model=self._model,
            conversation_key=conversation_key,
            delivery_target=delivery_target,
            delivery_user_id=delivery_user_id,
            mentioned_user_ids=mentioned_user_ids,
            agent_context=agent_context,
            access=self._access,
        )
        model_task = "\n".join(part for part in (task.strip(), agent_context.strip()) if part)
        turn = await self._request_turn(model_task, run=run)
        run.state = turn.state
        if plan_only:
            if not turn.ok or turn.decision.kind == "error":
                return f"智能体计划未通过：{turn.decision.error or '模型请求失败'}"
            token = self._new_token()
            self._plans[token] = PlannedAgentRun(
                token=token,
                run=run,
                decision=turn.decision,
                operator_id=operator_id,
                scope_id=scope_id,
                expires_at=self._clock() + self._plan_ttl_seconds,
            )
            if turn.decision.kind == "final":
                return f"智能体计划：无需调用工具。\n{turn.decision.answer}"
            tool = self._tools.get(turn.decision.tool)
            if tool is None:
                return "智能体请求了不可用工具，已拒绝执行。"
            arguments, error = self._validate_arguments(tool, turn.decision.arguments)
            if error:
                return f"智能体工具参数未通过本地校验：{error}"
            if tool.argument_validator is not None and (error := tool.argument_validator(arguments)):
                return f"智能体工具参数未通过本地校验：{error}"
            if tool.run_argument_validator is not None and (error := tool.run_argument_validator(arguments, run)):
                return f"智能体工具参数未通过本地校验：{error}"
            return "\n".join([
                "智能体首步计划（未执行）",
                f"建议：{turn.decision.summary or tool.description}",
                f"工具：{tool.name}",
                f"权限：{_PERMISSION_NAMES[tool.permission]}",
                f"参数：{self._format_arguments(tool, arguments)}",
                f"发送“智能体 执行 {token}”开始执行；计划 {self._plan_ttl_seconds} 秒内有效。",
            ])
        return await self._handle_turn(turn, run)

    async def _execute_plan(self, token: str, operator_id: str, scope_id: str) -> str:
        plan = self._plans.pop(token, None)
        if plan is None:
            return "未找到可执行的智能体计划，可能已执行、取消或过期。"
        if plan.expires_at <= self._clock():
            return "智能体计划已过期，未执行任何工具。"
        if plan.operator_id != operator_id or plan.scope_id != scope_id:
            self._plans[token] = plan
            return "该智能体计划只能由原操作者在原聊天范围执行。"
        if plan.decision.kind == "final":
            return plan.decision.answer
        return await self._handle_turn(AgentTurn(True, plan.run.state, plan.decision), plan.run)

    async def _confirm(self, token: str, operator_id: str, scope_id: str) -> str:
        action = self._pending.get(token)
        if action is None:
            return "未找到待确认操作，可能已取消、执行或过期。"
        if action.expires_at <= self._clock():
            self._pending.pop(token, None)
            return "待确认操作已过期，未执行任何操作。"
        if action.operator_id != operator_id or action.scope_id != scope_id:
            return "该待确认操作只能由原操作者在原聊天范围确认。"
        self._pending.pop(token, None)
        self._audit.record("确认已完成", action.tool.name, _PERMISSION_NAMES[action.tool.permission])
        result = await self._call_tool(action.tool, action.arguments, action.run)
        if action.run is None:
            return result.output
        return await self._continue_after_result(action.run, result)

    def _cancel(self, token: str, operator_id: str, scope_id: str) -> str:
        action = self._pending.get(token)
        if action is None:
            return "未找到待确认操作，可能已取消、执行或过期。"
        if action.operator_id != operator_id or action.scope_id != scope_id:
            return "该待确认操作只能由原操作者在原聊天范围取消。"
        self._pending.pop(token, None)
        self._audit.record("确认已取消", action.tool.name, _PERMISSION_NAMES[action.tool.permission])
        return "已取消待确认操作，未执行任何工具。"

    def _authorization_list(self, operator_id: str, scope_id: str) -> str:
        self._discard_expired()
        entries = [
            (permission, expires_at)
            for (owner, scope, permission), expires_at in self._approvals.items()
            if owner == operator_id and scope == scope_id
        ]
        if not entries:
            return "当前聊天范围没有临时智能体授权。"
        now = self._clock()
        return "\n".join([
            "当前聊天范围的临时智能体授权",
            *(f"- {_PERMISSION_NAMES[permission]}：剩余约 {max(0, int(expires_at - now))} 秒" for permission, expires_at in entries),
        ])

    def _request_authorization(self, value: str, operator_id: str, scope_id: str) -> str:
        normalized = value.strip().lower()
        permission = next((item for item, label in _PERMISSION_NAMES.items() if normalized in {item.value, label.lower()}), None)
        if permission not in _GRANTABLE_PERMISSIONS:
            return "当前仅允许申请“本机只读”临时授权；网络、写入、进程控制和高风险操作必须逐次确认。"
        token = self._new_token()

        async def grant(_: dict[str, str]) -> str:
            self._approvals[(operator_id, scope_id, permission)] = self._clock() + self._session_approval_ttl_seconds
            self._audit.record("临时授权已授予", _PERMISSION_NAMES[permission], _PERMISSION_NAMES[permission])
            return f"已授予当前聊天范围的“{_PERMISSION_NAMES[permission]}”临时授权，有效约 {self._session_approval_ttl_seconds} 秒。"

        self._pending[token] = PendingAgentAction(
            token=token,
            tool=AgentTool(f"临时授权：{_PERMISSION_NAMES[permission]}", "授予低风险临时权限", permission, AgentApproval.CONFIRM, grant),
            arguments={},
            run=None,
            operator_id=operator_id,
            scope_id=scope_id,
            expires_at=self._clock() + self._confirmation_ttl_seconds,
            direct=True,
        )
        return self._pending_message(self._pending[token])

    def _revoke_authorization(self, operator_id: str, scope_id: str) -> str:
        removed = 0
        for permission in _GRANTABLE_PERMISSIONS:
            if self._approvals.pop((operator_id, scope_id, permission), None) is not None:
                removed += 1
        return "已撤销当前聊天范围的临时授权。" if removed else "当前聊天范围没有可撤销的临时授权。"

    async def _direct_tool(self, name: str, operator_id: str, scope_id: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return "未找到该智能体工具。请先使用“智能体 工具”查看可用项。"
        if tool.parameters:
            return "该工具需要由模型根据任务填写参数；请直接描述任务，例如“智能体 在工作区创建 hello.txt”。"
        if tool.approval is AgentApproval.CONFIRM and not self._has_session_approval(tool.permission, operator_id, scope_id):
            return self._queue_confirmation(tool, {}, None, operator_id, scope_id, direct=True)
        return (await self._call_tool(tool, {})).output

    async def execute(
        self,
        value: str,
        *,
        operator_id: str,
        scope_id: str,
        conversation_key: ConversationKey | None = None,
        delivery_target: dict[str, Any] | None = None,
        delivery_user_id: str = "",
        mentioned_user_ids: tuple[str, ...] = (),
        agent_context: str = "",
    ) -> str:
        """处理 Bot 命令文本；所有自然语言任务走核心多轮 Agent 协议。"""
        normalized = value.strip()
        self._discard_expired()
        if normalized in {"", "帮助", "工具"}:
            return self.help_text()
        if normalized.startswith("确认 "):
            return await self._confirm(normalized.removeprefix("确认 ").strip(), operator_id, scope_id)
        if normalized.startswith("取消 "):
            return self._cancel(normalized.removeprefix("取消 ").strip(), operator_id, scope_id)
        if normalized == "授权列表":
            if self._access is not AgentAccess.SUPERUSER:
                return "当前安全智能体不提供本机权限授权。"
            return self._authorization_list(operator_id, scope_id)
        if normalized == "授权":
            if self._access is not AgentAccess.SUPERUSER:
                return "当前安全智能体不提供本机权限授权。"
            return "可申请的临时授权：本机只读。用法：智能体 授权 本机只读"
        if normalized.startswith("授权 "):
            if self._access is not AgentAccess.SUPERUSER:
                return "当前安全智能体不提供本机权限授权。"
            return self._request_authorization(normalized.removeprefix("授权 ").strip(), operator_id, scope_id)
        if normalized.startswith("撤销授权"):
            if self._access is not AgentAccess.SUPERUSER:
                return "当前安全智能体不提供本机权限授权。"
            return self._revoke_authorization(operator_id, scope_id)
        if normalized == "审计":
            if self._access is not AgentAccess.SUPERUSER:
                return "当前安全智能体不提供运行审计查询。"
            return self._audit.format()
        if normalized.startswith("审计 "):
            if self._access is not AgentAccess.SUPERUSER:
                return "当前安全智能体不提供运行审计查询。"
            try:
                return self._audit.format(int(normalized.removeprefix("审计 ").strip()))
            except ValueError:
                return "审计数量应为 1 到 50 的整数。"
        if normalized == "计划":
            return "请提供任务，例如：智能体 计划 在工作区创建 hello.txt，内容为 hello from agent"
        if normalized.startswith("计划 "):
            return await self._start(
                normalized.removeprefix("计划 ").strip(), operator_id, scope_id,
                plan_only=True, conversation_key=conversation_key,
                delivery_target=delivery_target, delivery_user_id=delivery_user_id,
                mentioned_user_ids=mentioned_user_ids, agent_context=agent_context,
            )
        if normalized == "执行":
            return "请提供任务，或使用“智能体 执行 <计划编号>”执行已有首步计划。"
        if normalized.startswith("执行 "):
            subject = normalized.removeprefix("执行 ").strip()
            if subject in self._plans:
                return await self._execute_plan(subject, operator_id, scope_id)
            return await self._start(
                subject, operator_id, scope_id,
                plan_only=False, conversation_key=conversation_key,
                delivery_target=delivery_target, delivery_user_id=delivery_user_id,
                mentioned_user_ids=mentioned_user_ids, agent_context=agent_context,
            )
        if normalized in self._tools:
            if self._tools[normalized].run_handler is not None:
                return await self._start(
                    normalized,
                    operator_id,
                    scope_id,
                    plan_only=False,
                    conversation_key=conversation_key,
                    delivery_target=delivery_target,
                    delivery_user_id=delivery_user_id,
                    mentioned_user_ids=mentioned_user_ids,
                    agent_context=agent_context,
                )
            return await self._direct_tool(normalized, operator_id, scope_id)
        # 除保留的控制子命令外，所有文本都是自然语言任务。不要求用户先
        # 写“执行”，这样“智能体 查看当前 IP”能直接进入模型决策循环。
        return await self._start(
            normalized,
            operator_id,
            scope_id,
            plan_only=False,
            conversation_key=conversation_key,
            delivery_target=delivery_target,
            delivery_user_id=delivery_user_id,
            mentioned_user_ids=mentioned_user_ids,
            agent_context=agent_context,
        )


def _format_model_catalog(catalog: dict[str, Any]) -> str:
    local = catalog.get("local")
    if not isinstance(local, dict):
        return "模型目录暂不可用。"
    lines = ["模型目录（本地静态配置）"]
    for category, label in (("free", "免费模型"), ("plus", "付费模型")):
        models = local.get(category)
        if not isinstance(models, dict) or not models:
            lines.append(f"{label}：无")
            continue
        entries = [f"{alias} -> {model}" for alias, model in models.items()]
        lines.append(f"{label}（{len(entries)}）：{'；'.join(entries[:12])}")
    return "\n".join(lines)


async def _raise_direct_only(_: dict[str, str]) -> str:
    """占位处理器：带运行上下文的工具不能绕过 AgentRun 直接调用。"""
    raise RuntimeError("该工具只能在智能体任务中调用")


def create_agent_runtime(
    service: ChatService,
    *,
    confirmation_ttl_seconds: int = 60,
    session_approval_ttl_seconds: int = 1800,
    plan_ttl_seconds: int = 300,
    max_steps: int = 8,
    model: str = "auto",
    workspace: Any = None,
    managed_services: ManagedServiceRegistry | None = None,
    command_runner: CommandRunner | None = None,
    filesystem_scanner: AgentFilesystemScanner | None = None,
    command_skills: Iterable[DeclarativeCommandSkill] = (),
    tool_providers: Iterable[AgentToolProvider] = (),
    agent_service: AgentService | None = None,
    agent_turn: AgentTurnHandler | None = None,
    schedule_reminder: ReminderScheduleHandler | None = None,
    schedule_target_reminder: TargetReminderScheduleHandler | None = None,
    reminder_operation: ReminderOperationHandler | None = None,
    final_renderer: AgentFinalRenderer | None = None,
    access: AgentAccess = AgentAccess.SUPERUSER,
    token_factory: Callable[[], str] = lambda: token_urlsafe(6),
) -> AgentRuntime:
    """创建默认本地工具集；工具执行始终受本文件的边界限制。"""
    registry = managed_services or ManagedServiceRegistry([], [])

    async def account_status(_: dict[str, str]) -> str:
        return format_account_status(await service.get_account_status())

    async def model_catalog(_: dict[str, str]) -> str:
        return _format_model_catalog(await service.get_model_catalog(fetch_remote=False))

    async def environment(_: dict[str, str]) -> str:
        return format_environment_diagnostics(collect_environment_diagnostics())

    tools = [
        AgentTool("状态", "查看 ChatGPT 账户与浏览器运行诊断", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, account_status),
        AgentTool("模型", "查看已缓存的模型目录", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, model_catalog),
        AgentTool("环境", "查看本机实时内存使用率、可用内存、磁盘和系统负载等基础环境诊断", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, environment),
    ]
    if command_runner is not None:
        async def run_command(arguments: dict[str, str]) -> str:
            return await command_runner.run(arguments)

        def validate_command(arguments: dict[str, str]) -> str:
            try:
                command_runner.parse(arguments)
            except CommandValidationError as error:
                return str(error)
            return ""

        tools.append(AgentTool(
            "运行系统命令",
            "使用明确的程序和 JSON argv 执行一次跨平台系统命令。不会运行 shell 字符串；必须经超级用户确认。",
            AgentPermission.PROCESS_CONTROL,
            AgentApproval.CONFIRM,
            run_command,
            (
                AgentToolParameter("程序", "可执行程序路径或命令名"),
                AgentToolParameter("参数", "JSON 字符串数组，例如 [\"--version\"]"),
                AgentToolParameter("工作目录", "可选工作目录；未填写时使用配置的命令目录", required=False),
                AgentToolParameter("超时秒数", "可选整数，1 到 600", required=False),
            ),
            lambda arguments: command_runner.parse(arguments).display(),
            argument_validator=validate_command,
        ))
        for skill in command_skills:
            async def run_command_skill(arguments: dict[str, str], *, definition: DeclarativeCommandSkill = skill) -> str:
                return await command_runner.run(definition.command_arguments(arguments))

            def validate_command_skill(arguments: dict[str, str], *, definition: DeclarativeCommandSkill = skill) -> str:
                if error := definition.validate(arguments):
                    return error
                try:
                    command_runner.parse(definition.command_arguments(arguments))
                except (AgentSkillError, CommandValidationError) as error:
                    return str(error)
                return ""

            parameters = tuple(
                AgentToolParameter(parameter.name, parameter.description, parameter.required, parameter.choices)
                for parameter in skill.parameters
            )
            tools.append(AgentTool(
                f"技能：{skill.name}",
                f"管理员配置的受控技能：{skill.description}。程序和 argv 结构固定，参数会在本地校验；每次执行需超级用户确认。",
                AgentPermission.PROCESS_CONTROL,
                AgentApproval.CONFIRM,
                run_command_skill,
                parameters,
                lambda arguments, definition=skill: f"技能：{definition.name}\n{command_runner.parse(definition.command_arguments(arguments)).display()}",
                argument_validator=validate_command_skill,
            ))
    if filesystem_scanner is not None and filesystem_scanner.root_choices:
        async def scan_filesystem(arguments: dict[str, str]) -> str:
            return await asyncio.to_thread(filesystem_scanner.scan, arguments)

        def validate_filesystem_scan(arguments: dict[str, str]) -> str:
            return filesystem_scanner.validate(arguments)

        tools.append(AgentTool(
            "扫描目录占用",
            "在管理员明确配置的目录中扫描文件与子目录占用；不跟随符号链接，不会读取文件正文或修改任何数据。",
            AgentPermission.READ_LOCAL,
            AgentApproval.CONFIRM,
            scan_filesystem,
            (
                AgentToolParameter("扫描目录", "管理员配置的允许扫描目录", choices=filesystem_scanner.root_choices),
                AgentToolParameter("最大深度", f"可选整数，1 到 6；默认 3", required=False),
                AgentToolParameter("结果数量", f"可选整数，1 到 {200}；默认 20", required=False),
            ),
            lambda arguments: f"扫描目录占用：{arguments['扫描目录']}（最大深度 {arguments.get('最大深度', '3')}，最多显示 {arguments.get('结果数量', '20')} 项）",
            argument_validator=validate_filesystem_scan,
        ))
    def validate_reminder(arguments: dict[str, str]) -> str:
        try:
            delay_seconds = int(arguments["延迟秒数"])
        except ValueError:
            return "提醒延迟必须是整数秒。"
        if not 1 <= delay_seconds <= 604800:
            return "提醒延迟必须在 1 秒到 7 天之间。"
        if not arguments["内容"].strip():
            return "提醒内容不能为空。"
        return ""

    if schedule_reminder is not None:
        async def schedule_reminder_tool(arguments: dict[str, str], run: AgentRun) -> str:
            try:
                delay_seconds = int(arguments["延迟秒数"])
            except ValueError:
                return "提醒延迟必须是整数秒。"
            if not 1 <= delay_seconds <= 604800:
                return "提醒延迟必须在 1 秒到 7 天之间。"
            return await schedule_reminder(run, delay_seconds, arguments["内容"])

        tools.append(AgentTool(
            "安排提醒",
            "在原聊天范围安排一次提醒。仅可提醒发起任务的用户；到时会回到同一逻辑会话，按当前人设生成提醒。",
            AgentPermission.MESSAGE_SEND,
            AgentApproval.AUTOMATIC,
            _raise_direct_only,
            (
                AgentToolParameter("延迟秒数", "距现在的整数秒数，范围 1 到 604800"),
                AgentToolParameter("内容", "提醒内容"),
            ),
            lambda arguments: f"在 {arguments['延迟秒数']} 秒后提醒：{arguments['内容'][:120]}",
            run_handler=schedule_reminder_tool,
            argument_validator=validate_reminder,
            minimum_access=AgentAccess.MEMBER,
        ))
    if schedule_target_reminder is not None:
        def validate_target_reminder(arguments: dict[str, str], run: AgentRun) -> str:
            if arguments["对象ID"].strip() not in run.mentioned_user_ids:
                return "只能提醒本条消息中实际提及的用户。"
            return ""

        async def schedule_target_reminder_tool(arguments: dict[str, str], run: AgentRun) -> str:
            try:
                delay_seconds = int(arguments["延迟秒数"])
            except ValueError:
                return "提醒延迟必须是整数秒。"
            return await schedule_target_reminder(
                run,
                delay_seconds,
                arguments["内容"],
                arguments["对象ID"].strip(),
            )

        tools.append(AgentTool(
            "安排指定提醒",
            "在原聊天范围安排一次对已提及成员的提醒。对象 ID 必须来自本条消息的 @ 提及；该消息投递需要超级用户确认。",
            AgentPermission.MESSAGE_SEND,
            AgentApproval.CONFIRM,
            _raise_direct_only,
            (
                AgentToolParameter("延迟秒数", "距现在的整数秒数，范围 1 到 604800"),
                AgentToolParameter("对象ID", "本条消息 @ 提及的对象 ID"),
                AgentToolParameter("内容", "提醒内容"),
            ),
            lambda arguments: f"在 {arguments['延迟秒数']} 秒后提醒对象 {arguments['对象ID']}：{arguments['内容'][:120]}",
            run_handler=schedule_target_reminder_tool,
            argument_validator=validate_reminder,
            run_argument_validator=validate_target_reminder,
        ))
    if workspace is not None:
        agent_workspace = AgentWorkspace(workspace)

        async def list_files(arguments: dict[str, str]) -> str:
            try:
                return agent_workspace.list_files(arguments.get("路径", ""))
            except WorkspaceError as error:
                return f"工作目录操作已拒绝：{error}"

        async def read_file(arguments: dict[str, str]) -> str:
            try:
                return agent_workspace.read_text(arguments["路径"])
            except WorkspaceError as error:
                return f"工作目录操作已拒绝：{error}"

        async def write_file(arguments: dict[str, str]) -> str:
            try:
                return agent_workspace.write_text(arguments["路径"], arguments["内容"])
            except WorkspaceError as error:
                return f"工作目录操作已拒绝：{error}"

        tools.extend([
            AgentTool("列出工作区文件", "列出受限工作目录内的文件和目录", AgentPermission.READ_LOCAL, AgentApproval.CONFIRM, list_files, (AgentToolParameter("路径", "工作目录内相对目录，可省略", required=False),)),
            AgentTool("读取工作区文件", "读取受限工作目录内的一个 UTF-8 文本文件", AgentPermission.READ_LOCAL, AgentApproval.CONFIRM, read_file, (AgentToolParameter("路径", "工作目录内相对文件路径"),), lambda arguments: f"读取工作目录文件 {arguments['路径']}"),
            AgentTool("写入工作区文件", "以 UTF-8 原子写入受限工作目录内的一个文件", AgentPermission.WRITE_LOCAL, AgentApproval.CONFIRM, write_file, (AgentToolParameter("路径", "工作目录内相对文件路径"), AgentToolParameter("内容", "要写入的 UTF-8 文本", sensitive=True)), lambda arguments: f"写入工作目录文件 {arguments['路径']}（内容不在确认消息中展示）"),
        ])
    if registry.process_names or registry.tcp_names:
        async def service_overview(_: dict[str, str]) -> str:
            return await registry.overview()

        tools.append(AgentTool(
            "受管服务概览",
            "汇总已配置服务的状态与重启权限",
            AgentPermission.READ_NETWORK if registry.tcp_names else AgentPermission.READ_LOCAL,
            AgentApproval.CONFIRM if registry.tcp_names else AgentApproval.AUTOMATIC,
            service_overview,
        ))
    if registry.process_names:
        async def process_status(arguments: dict[str, str]) -> str:
            return registry.process_status(arguments["服务"])

        tools.append(AgentTool("本地服务状态", "查看已配置 PID 服务的状态", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, process_status, (AgentToolParameter("服务", "已配置服务名", choices=registry.process_names),)))
    if registry.tcp_names:
        async def tcp_status(arguments: dict[str, str]) -> str:
            return await registry.tcp_status(arguments["服务"])

        tools.append(AgentTool("网络服务状态", "探测已配置 TCP 服务的连通性", AgentPermission.READ_NETWORK, AgentApproval.CONFIRM, tcp_status, (AgentToolParameter("服务", "已配置服务名", choices=registry.tcp_names),)))
    if registry.restart_names:
        async def restart_service(arguments: dict[str, str]) -> str:
            return await registry.restart(arguments["服务"])

        tools.append(AgentTool("重启受管服务", "使用管理员预配置命令重启指定服务", AgentPermission.PROCESS_CONTROL, AgentApproval.CONFIRM, restart_service, (AgentToolParameter("服务", "允许重启的服务名", choices=registry.restart_names),), lambda arguments: f"重启受管服务 {arguments['服务']}（使用管理员配置）"))
    if reminder_operation is not None:
        async def list_reminders(_: dict[str, str], run: AgentRun) -> str:
            return await reminder_operation(run, "list", "")

        async def cancel_reminder(arguments: dict[str, str], run: AgentRun) -> str:
            return await reminder_operation(run, "cancel", arguments["编号"])

        tools.extend([
            AgentTool(
                "查看我的提醒",
                "列出当前用户在当前聊天范围创建、尚未到期的提醒。",
                AgentPermission.MESSAGE_SEND,
                AgentApproval.AUTOMATIC,
                _raise_direct_only,
                run_handler=list_reminders,
                minimum_access=AgentAccess.MEMBER,
            ),
            AgentTool(
                "取消我的提醒",
                "取消当前用户在当前聊天范围创建的一条提醒。",
                AgentPermission.MESSAGE_SEND,
                AgentApproval.AUTOMATIC,
                _raise_direct_only,
                (AgentToolParameter("编号", "要取消的提醒编号"),),
                lambda arguments: f"取消自己的提醒 {arguments['编号']}",
                run_handler=cancel_reminder,
                minimum_access=AgentAccess.MEMBER,
            ),
        ])
    for provider in (*_TOOL_PROVIDERS, *tool_providers):
        try:
            tools.extend(provider(access))
        except Exception as error:
            raise RuntimeError("智能体附加工具提供者初始化失败。") from error
    visible_tools = [tool for tool in tools if tool.minimum_access is AgentAccess.MEMBER or access is AgentAccess.SUPERUSER]
    return AgentRuntime(
        service,
        visible_tools,
        confirmation_ttl_seconds=confirmation_ttl_seconds,
        session_approval_ttl_seconds=session_approval_ttl_seconds,
        plan_ttl_seconds=plan_ttl_seconds,
        max_steps=max_steps,
        model=model,
        agent_service=agent_service,
        agent_turn=agent_turn,
        schedule_reminder=schedule_reminder,
        schedule_target_reminder=schedule_target_reminder,
        reminder_operation=reminder_operation,
        final_renderer=final_renderer,
        access=access,
        token_factory=token_factory,
    )
