"""仅供超级用户调用的受控 Agent 工具基础。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from secrets import token_urlsafe
from time import monotonic
from typing import Any

from ChatGPTWeb import ChatService

from .environment_diagnostics import collect_environment_diagnostics, format_environment_diagnostics
from .management_views import format_account_status


AgentToolHandler = Callable[[], Awaitable[str]]


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


@dataclass(frozen=True)
class AgentTool:
    """一个由插件明确注册、可独立审计的 Agent 工具。"""

    name: str
    description: str
    permission: AgentPermission
    approval: AgentApproval
    handler: AgentToolHandler


@dataclass(frozen=True)
class PendingAgentAction:
    """等待同一操作者在同一聊天范围确认的一次性操作。"""

    token: str
    tool: AgentTool
    operator_id: str
    scope_id: str
    expires_at: float


class AgentRuntime:
    """管理只读工具，并为后续确认式写操作保留统一入口。"""

    def __init__(
        self,
        tools: list[AgentTool],
        *,
        confirmation_ttl_seconds: int = 60,
        clock: Callable[[], float] = monotonic,
        token_factory: Callable[[], str] = lambda: token_urlsafe(6),
    ):
        self._tools = {tool.name: tool for tool in tools}
        self._confirmation_ttl_seconds = confirmation_ttl_seconds
        self._clock = clock
        self._token_factory = token_factory
        self._pending: dict[str, PendingAgentAction] = {}

    def help_text(self) -> str:
        lines = ["智能体工具（仅超级用户）"]
        for tool in self._tools.values():
            confirmation = "需确认" if tool.approval is AgentApproval.CONFIRM else "自动允许"
            lines.append(
                f"- {tool.name}：{tool.description}（{_PERMISSION_NAMES[tool.permission]}，{confirmation}）"
            )
        lines.append("用法：智能体 工具 / 智能体 状态 / 智能体 模型")
        lines.append("需确认的操作会返回一次性编号，请在同一聊天范围发送：智能体 确认 <编号>")
        return "\n".join(lines)

    def _discard_expired(self) -> None:
        now = self._clock()
        self._pending = {
            token: action
            for token, action in self._pending.items()
            if action.expires_at > now
        }

    def _create_pending(self, tool: AgentTool, operator_id: str, scope_id: str) -> str:
        self._discard_expired()
        token = self._token_factory()
        while token in self._pending:
            token = self._token_factory()
        self._pending[token] = PendingAgentAction(
            token=token,
            tool=tool,
            operator_id=operator_id,
            scope_id=scope_id,
            expires_at=self._clock() + self._confirmation_ttl_seconds,
        )
        return token

    async def _confirm(self, token: str, operator_id: str, scope_id: str) -> str:
        action = self._pending.pop(token, None)
        if action is None:
            return "未找到待确认操作，可能已取消、已执行或已过期。"
        if action.expires_at <= self._clock():
            return "待确认操作已过期，未执行任何操作。"
        if action.operator_id != operator_id or action.scope_id != scope_id:
            self._pending[token] = action
            return "该待确认操作只能由原操作者在原聊天范围确认。"
        return await action.tool.handler()

    def _cancel(self, token: str, operator_id: str, scope_id: str) -> str:
        action = self._pending.get(token)
        if action is None:
            return "未找到待确认操作，可能已取消、已执行或已过期。"
        if action.expires_at <= self._clock():
            self._pending.pop(token, None)
            return "待确认操作已过期，未执行任何操作。"
        if action.operator_id != operator_id or action.scope_id != scope_id:
            return "该待确认操作只能由原操作者在原聊天范围取消。"
        self._pending.pop(token, None)
        return "已取消待确认操作，未执行任何操作。"

    async def execute(self, name: str, *, operator_id: str, scope_id: str) -> str:
        normalized = name.strip()
        if normalized.startswith("确认 "):
            return await self._confirm(normalized.removeprefix("确认 ").strip(), operator_id, scope_id)
        if normalized.startswith("取消 "):
            return self._cancel(normalized.removeprefix("取消 ").strip(), operator_id, scope_id)
        self._discard_expired()
        if normalized in {"", "帮助", "工具"}:
            return self.help_text()
        tool = self._tools.get(normalized)
        if tool is None:
            return "未找到该智能体工具。请先使用“智能体 工具”查看可用项。"
        if tool.approval is AgentApproval.CONFIRM:
            token = self._create_pending(tool, operator_id, scope_id)
            return (
                f"已创建“{tool.name}”待确认操作（权限：{_PERMISSION_NAMES[tool.permission]}），"
                f"请在 {self._confirmation_ttl_seconds} 秒内发送“智能体 确认 {token}”。"
            )
        return await tool.handler()


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


def create_agent_runtime(service: ChatService, *, confirmation_ttl_seconds: int = 60) -> AgentRuntime:
    """创建默认只读工具集，不触发远程能力刷新或任何账户操作。"""

    async def account_status() -> str:
        return format_account_status(await service.get_account_status())

    async def model_catalog() -> str:
        return _format_model_catalog(await service.get_model_catalog(fetch_remote=False))

    async def confirmation_demo() -> str:
        return "确认事务已完成，未执行外部操作。"

    async def environment() -> str:
        return format_environment_diagnostics(collect_environment_diagnostics())

    return AgentRuntime([
        AgentTool("状态", "查看账户与浏览器运行诊断", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, account_status),
        AgentTool("模型", "查看本地配置的模型别名", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, model_catalog),
        AgentTool("环境", "查看跨平台本机基础环境诊断", AgentPermission.READ_LOCAL, AgentApproval.AUTOMATIC, environment),
        AgentTool("确认演示", "验证确认流程，不执行外部操作", AgentPermission.READ_LOCAL, AgentApproval.CONFIRM, confirmation_demo),
    ], confirmation_ttl_seconds=confirmation_ttl_seconds)
