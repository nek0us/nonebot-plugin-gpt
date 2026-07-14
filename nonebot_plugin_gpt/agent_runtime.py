"""仅供超级用户调用的受控 Agent 工具与审批基础。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from secrets import token_urlsafe
from time import monotonic
from typing import Any

from ChatGPTWeb import ChatService

from .agent_audit import AgentAuditLog
from .agent_planner import AgentPlanner
from .environment_diagnostics import collect_environment_diagnostics, format_environment_diagnostics
from .management_views import format_account_status


AgentActionHandler = Callable[[dict[str, str]], Awaitable[str]]


class AgentPermission(str, Enum):
    """工具实际能力类别；它是代码校验依据，不是提示词约定。"""

    READ_LOCAL = "read_local"
    READ_NETWORK = "read_network"
    WRITE_LOCAL = "write_local"
    PROCESS_CONTROL = "process_control"
    DESTRUCTIVE = "destructive"


class AgentApproval(str, Enum):
    """单个工具的审批策略。"""

    AUTOMATIC = "automatic"
    CONFIRM = "confirm"


_PERMISSION_NAMES = {
    AgentPermission.READ_LOCAL: "本机只读",
    AgentPermission.READ_NETWORK: "网络读取",
    AgentPermission.WRITE_LOCAL: "本机写入",
    AgentPermission.PROCESS_CONTROL: "进程控制",
    AgentPermission.DESTRUCTIVE: "高风险变更",
}
_GRANTABLE_PERMISSIONS = {AgentPermission.READ_LOCAL}


@dataclass(frozen=True)
class AgentTool:
    """一个由插件明确注册、可独立审计的 Agent 工具。"""

    name: str
    description: str
    permission: AgentPermission
    approval: AgentApproval
    handler: AgentActionHandler
    parameters: tuple["AgentToolParameter", ...] = ()


@dataclass(frozen=True)
class AgentToolParameter:
    """一个由插件本地校验的工具参数。"""

    name: str
    description: str
    required: bool = True
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class PendingAgentAction:
    """等待同一操作者在同一聊天范围确认的一次性操作。"""

    token: str
    name: str
    description: str
    permission: AgentPermission
    handler: AgentActionHandler
    operator_id: str
    scope_id: str
    expires_at: float


@dataclass(frozen=True)
class PlannedAgentAction:
    """已由本地校验通过、尚未执行的工具计划。"""

    token: str
    tool: AgentTool
    reason: str
    arguments: dict[str, str]
    operator_id: str
    scope_id: str
    expires_at: float


class AgentRuntime:
    """管理工具、一次性确认与低风险临时授权。"""

    def __init__(
        self,
        tools: list[AgentTool],
        *,
        confirmation_ttl_seconds: int = 60,
        session_approval_ttl_seconds: int = 1800,
        plan_ttl_seconds: int = 300,
        planner: AgentPlanner | None = None,
        audit_log: AgentAuditLog | None = None,
        clock: Callable[[], float] = monotonic,
        token_factory: Callable[[], str] = lambda: token_urlsafe(6),
    ):
        self._tools = {tool.name: tool for tool in tools}
        self._confirmation_ttl_seconds = confirmation_ttl_seconds
        self._session_approval_ttl_seconds = session_approval_ttl_seconds
        self._plan_ttl_seconds = plan_ttl_seconds
        self._clock = clock
        self._token_factory = token_factory
        self._planner = planner
        self._audit = audit_log or AgentAuditLog()
        self._pending: dict[str, PendingAgentAction] = {}
        self._plans: dict[str, PlannedAgentAction] = {}
        self._approvals: dict[tuple[str, str, AgentPermission], float] = {}

    def help_text(self) -> str:
        lines = ["智能体工具（仅超级用户）"]
        for tool in self._tools.values():
            confirmation = "需确认" if tool.approval is AgentApproval.CONFIRM else "自动允许"
            lines.append(
                f"- {tool.name}：{tool.description}（{_PERMISSION_NAMES[tool.permission]}，{confirmation}）"
            )
        lines.extend([
            "用法：智能体 工具 / 智能体 状态 / 智能体 模型 / 智能体 环境",
            "模型规划：智能体 计划 <任务>。计划只提出建议，不会执行工具。",
            "执行已校验计划：智能体 执行 <计划编号>。计划仅在原聊天范围内短期有效。",
            "查看审计：智能体 审计 [数量]。审计仅保留当前运行的无敏感事件。",
            "需确认的操作会返回一次性编号，请在同一聊天范围发送：智能体 确认 <编号>",
            "可申请临时授权：智能体 授权 本机只读；可用 授权列表 或 撤销授权 查看和撤销。",
        ])
        return "\n".join(lines)

    def _planner_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "permission": _PERMISSION_NAMES[tool.permission],
                "approval": "需确认" if tool.approval is AgentApproval.CONFIRM else "自动允许",
                "parameters": [
                    {"name": item.name, "description": item.description, "required": item.required, "choices": list(item.choices)}
                    for item in tool.parameters
                ],
            }
            for tool in self._tools.values()
        ]

    async def _plan_task(self, task: str, operator_id: str, scope_id: str) -> str:
        if self._planner is None:
            self._audit.record("计划被拒绝", "模型规划器")
            return "模型规划器尚未配置。"
        plan = await self._planner.plan(task, self._planner_tools())
        if not plan.valid:
            self._audit.record("计划被拒绝", "模型规划")
            return f"智能体计划未通过校验：{plan.error}"
        if plan.tool_name is None:
            self._audit.record("计划未调用工具", "模型规划")
            return f"智能体计划（未执行）\n当前不建议调用工具。\n理由：{plan.reason}"
        tool = self._tools[plan.tool_name]
        arguments, error = self._validate_tool_arguments(tool, plan.arguments)
        if error:
            self._audit.record("计划被拒绝", tool.name, _PERMISSION_NAMES[tool.permission])
            return f"智能体计划未通过参数校验：{error}"
        approval = "需确认" if tool.approval is AgentApproval.CONFIRM else "自动允许"
        token = self._new_token()
        self._plans[token] = PlannedAgentAction(
            token=token,
            tool=tool,
            reason=plan.reason,
            arguments=arguments,
            operator_id=operator_id,
            scope_id=scope_id,
            expires_at=self._clock() + self._plan_ttl_seconds,
        )
        self._audit.record("计划已创建", tool.name, _PERMISSION_NAMES[tool.permission])
        return "\n".join([
            "智能体计划（未执行）",
            f"建议工具：{tool.name}",
            f"权限：{_PERMISSION_NAMES[tool.permission]}｜审批：{approval}",
            f"理由：{plan.reason}",
            f"计划编号：{token}（{self._plan_ttl_seconds} 秒内有效）",
            f"如需执行，请发送“智能体 执行 {token}”。",
        ])

    def _discard_expired(self) -> None:
        now = self._clock()
        self._pending = {
            token: action
            for token, action in self._pending.items()
            if action.expires_at > now
        }
        self._plans = {
            token: plan
            for token, plan in self._plans.items()
            if plan.expires_at > now
        }
        self._approvals = {
            key: expires_at
            for key, expires_at in self._approvals.items()
            if expires_at > now
        }

    def _new_token(self) -> str:
        token = self._token_factory()
        while token in self._pending or token in self._plans:
            token = self._token_factory()
        return token

    @staticmethod
    def _validate_tool_arguments(tool: AgentTool, arguments: dict[str, str]) -> tuple[dict[str, str], str]:
        declared = {item.name: item for item in tool.parameters}
        unexpected = set(arguments) - set(declared)
        if unexpected:
            return {}, f"包含未声明参数：{'、'.join(sorted(unexpected))}"
        normalized = {}
        for name, parameter in declared.items():
            value = arguments.get(name)
            if value is None:
                if parameter.required:
                    return {}, f"缺少必填参数：{name}"
                continue
            if parameter.choices and value not in parameter.choices:
                return {}, f"参数 {name} 仅允许：{'、'.join(parameter.choices)}"
            normalized[name] = value
        return normalized, ""

    def _create_pending(
        self,
        *,
        name: str,
        description: str,
        permission: AgentPermission,
        handler: AgentActionHandler,
        operator_id: str,
        scope_id: str,
    ) -> str:
        self._discard_expired()
        token = self._new_token()
        self._pending[token] = PendingAgentAction(
            token=token,
            name=name,
            description=description,
            permission=permission,
            handler=handler,
            operator_id=operator_id,
            scope_id=scope_id,
            expires_at=self._clock() + self._confirmation_ttl_seconds,
        )
        return token

    @staticmethod
    def _approval_key(operator_id: str, scope_id: str, permission: AgentPermission) -> tuple[str, str, AgentPermission]:
        return operator_id, scope_id, permission

    def _has_session_approval(self, permission: AgentPermission, operator_id: str, scope_id: str) -> bool:
        expires_at = self._approvals.get(self._approval_key(operator_id, scope_id, permission), 0)
        return expires_at > self._clock()

    def _pending_message(self, action: PendingAgentAction) -> str:
        return (
            f"已创建“{action.name}”待确认操作（权限：{_PERMISSION_NAMES[action.permission]}）。\n"
            f"原因：{action.description}\n"
            f"请在 {self._confirmation_ttl_seconds} 秒内发送“智能体 确认 {action.token}”，"
            f"或发送“智能体 取消 {action.token}”。"
        )

    async def _confirm(self, token: str, operator_id: str, scope_id: str) -> str:
        action = self._pending.pop(token, None)
        if action is None:
            return "未找到待确认操作，可能已取消、已执行或已过期。"
        if action.expires_at <= self._clock():
            self._audit.record("确认已过期", action.name, _PERMISSION_NAMES[action.permission])
            return "待确认操作已过期，未执行任何操作。"
        if action.operator_id != operator_id or action.scope_id != scope_id:
            self._pending[token] = action
            self._audit.record("确认被拒绝", action.name, _PERMISSION_NAMES[action.permission])
            return "该待确认操作只能由原操作者在原聊天范围确认。"
        self._audit.record("确认已完成", action.name, _PERMISSION_NAMES[action.permission])
        return await action.handler()

    def _cancel(self, token: str, operator_id: str, scope_id: str) -> str:
        action = self._pending.get(token)
        if action is None:
            return "未找到待确认操作，可能已取消、已执行或已过期。"
        if action.expires_at <= self._clock():
            self._pending.pop(token, None)
            self._audit.record("确认已过期", action.name, _PERMISSION_NAMES[action.permission])
            return "待确认操作已过期，未执行任何操作。"
        if action.operator_id != operator_id or action.scope_id != scope_id:
            return "该待确认操作只能由原操作者在原聊天范围取消。"
        self._pending.pop(token, None)
        self._audit.record("确认已取消", action.name, _PERMISSION_NAMES[action.permission])
        return "已取消待确认操作，未执行任何操作。"

    def _permission_from_text(self, value: str) -> AgentPermission | None:
        normalized = value.strip().lower()
        for permission, label in _PERMISSION_NAMES.items():
            if normalized in {permission.value, label.lower()}:
                return permission
        return None

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
        lines = ["当前聊天范围的临时智能体授权"]
        for permission, expires_at in sorted(entries, key=lambda item: item[0].value):
            lines.append(f"- {_PERMISSION_NAMES[permission]}：剩余约 {max(0, int(expires_at - now))} 秒")
        return "\n".join(lines)

    def _revoke_authorization(self, value: str, operator_id: str, scope_id: str) -> str:
        self._discard_expired()
        permission = self._permission_from_text(value) if value.strip() else None
        if value.strip() and permission is None:
            return "未识别权限类别。当前仅支持“本机只读”。"
        targets = [permission] if permission else list(_GRANTABLE_PERMISSIONS)
        removed = 0
        for target in targets:
            if self._approvals.pop(self._approval_key(operator_id, scope_id, target), None) is not None:
                removed += 1
                self._audit.record("临时授权已撤销", _PERMISSION_NAMES[target], _PERMISSION_NAMES[target])
        return "已撤销当前聊天范围的临时授权。" if removed else "当前聊天范围没有可撤销的临时授权。"

    def _request_authorization(self, value: str, operator_id: str, scope_id: str) -> str:
        permission = self._permission_from_text(value)
        if permission not in _GRANTABLE_PERMISSIONS:
            return "当前仅允许申请“本机只读”临时授权；网络、写入、进程控制和高风险操作必须逐次确认。"

        async def grant() -> str:
            self._approvals[self._approval_key(operator_id, scope_id, permission)] = (
                self._clock() + self._session_approval_ttl_seconds
            )
            self._audit.record("临时授权已授予", _PERMISSION_NAMES[permission], _PERMISSION_NAMES[permission])
            return (
                f"已授予当前聊天范围的“{_PERMISSION_NAMES[permission]}”临时授权，"
                f"有效约 {self._session_approval_ttl_seconds} 秒；可随时使用“智能体 撤销授权”取消。"
            )

        token = self._create_pending(
            name=f"临时授权：{_PERMISSION_NAMES[permission]}",
            description="允许当前聊天范围内的同类低风险操作在有效期内免于重复确认。",
            permission=permission,
            handler=grant,
            operator_id=operator_id,
            scope_id=scope_id,
        )
        return self._pending_message(self._pending[token])

    async def _execute_tool(self, tool: AgentTool, arguments: dict[str, str], operator_id: str, scope_id: str) -> str:
        if tool.approval is AgentApproval.CONFIRM and not self._has_session_approval(
            tool.permission,
            operator_id,
            scope_id,
        ):
            token = self._create_pending(
                name=tool.name,
                description=tool.description,
                permission=tool.permission,
                handler=lambda: tool.handler(arguments),
                operator_id=operator_id,
                scope_id=scope_id,
            )
            self._audit.record("确认已创建", tool.name, _PERMISSION_NAMES[tool.permission])
            return self._pending_message(self._pending[token])
        self._audit.record("工具已执行", tool.name, _PERMISSION_NAMES[tool.permission])
        return await tool.handler(arguments)

    async def _execute_plan(self, token: str, operator_id: str, scope_id: str) -> str:
        plan = self._plans.pop(token, None)
        if plan is None:
            return "未找到可执行计划，可能已执行、已取消或已过期。"
        if plan.expires_at <= self._clock():
            self._audit.record("计划已过期", plan.tool.name, _PERMISSION_NAMES[plan.tool.permission])
            return "计划已过期，未执行任何工具。"
        if plan.operator_id != operator_id or plan.scope_id != scope_id:
            self._plans[token] = plan
            self._audit.record("计划执行被拒绝", plan.tool.name, _PERMISSION_NAMES[plan.tool.permission])
            return "该计划只能由原操作者在原聊天范围执行。"
        self._audit.record("计划已执行", plan.tool.name, _PERMISSION_NAMES[plan.tool.permission])
        return await self._execute_tool(plan.tool, plan.arguments, operator_id, scope_id)

    async def execute(self, name: str, *, operator_id: str, scope_id: str) -> str:
        normalized = name.strip()
        if normalized.startswith("确认 "):
            return await self._confirm(normalized.removeprefix("确认 ").strip(), operator_id, scope_id)
        if normalized.startswith("取消 "):
            return self._cancel(normalized.removeprefix("取消 ").strip(), operator_id, scope_id)
        if normalized.startswith("执行 "):
            return await self._execute_plan(normalized.removeprefix("执行 ").strip(), operator_id, scope_id)
        self._discard_expired()
        if normalized in {"", "帮助", "工具"}:
            return self.help_text()
        if normalized == "计划":
            return "请提供任务，例如：智能体 计划 检查当前运行环境"
        if normalized.startswith("计划 "):
            return await self._plan_task(normalized.removeprefix("计划 ").strip(), operator_id, scope_id)
        if normalized == "审计":
            return self._audit.format()
        if normalized.startswith("审计 "):
            try:
                limit = int(normalized.removeprefix("审计 ").strip())
            except ValueError:
                return "审计数量应为 1 到 50 的整数。"
            return self._audit.format(limit)
        if normalized == "授权列表":
            return self._authorization_list(operator_id, scope_id)
        if normalized == "授权":
            return "可申请的临时授权：本机只读。用法：智能体 授权 本机只读"
        if normalized.startswith("授权 "):
            return self._request_authorization(normalized.removeprefix("授权 ").strip(), operator_id, scope_id)
        if normalized == "撤销授权":
            return self._revoke_authorization("", operator_id, scope_id)
        if normalized.startswith("撤销授权 "):
            return self._revoke_authorization(normalized.removeprefix("撤销授权 ").strip(), operator_id, scope_id)
        tool = self._tools.get(normalized)
        if tool is None:
            return "未找到该智能体工具。请先使用“智能体 工具”查看可用项。"
        return await self._execute_tool(tool, {}, operator_id, scope_id)


def _format_model_catalog(catalog: dict[str, Any]) -> str:
    """以有限行数展示本地模型别名，避免目录过大淹没聊天窗口。"""
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
        preview = "；".join(entries[:12])
        suffix = f"；另有 {len(entries) - 12} 项" if len(entries) > 12 else ""
        lines.append(f"{label}（{len(entries)}）：{preview}{suffix}")
    return "\n".join(lines)


def create_agent_runtime(
    service: ChatService,
    *,
    confirmation_ttl_seconds: int = 60,
    session_approval_ttl_seconds: int = 1800,
    plan_ttl_seconds: int = 300,
) -> AgentRuntime:
    """创建默认工具集，不触发远程能力刷新或任何账户操作。"""

    async def account_status(_: dict[str, str]) -> str:
        return format_account_status(await service.get_account_status())

    async def model_catalog(_: dict[str, str]) -> str:
        return _format_model_catalog(await service.get_model_catalog(fetch_remote=False))

    async def confirmation_demo(_: dict[str, str]) -> str:
        return "确认事务已完成，未执行外部操作。"

    async def environment(_: dict[str, str]) -> str:
        return format_environment_diagnostics(collect_environment_diagnostics())

    return AgentRuntime([
        AgentTool("状态", "查看账户与浏览器运行诊断", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, account_status),
        AgentTool("模型", "查看本地配置的模型别名", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, model_catalog),
        AgentTool("环境", "查看跨平台本机基础环境诊断", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, environment),
        AgentTool("确认演示", "验证确认流程，不执行外部操作", AgentPermission.READ_LOCAL, AgentApproval.CONFIRM, confirmation_demo),
    ],
        confirmation_ttl_seconds=confirmation_ttl_seconds,
        session_approval_ttl_seconds=session_approval_ttl_seconds,
        plan_ttl_seconds=plan_ttl_seconds,
        planner=AgentPlanner(service),
    )
