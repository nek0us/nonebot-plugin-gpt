"""仅供超级用户调用的受控 Agent 工具基础。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ChatGPTWeb import ChatService

from .management_views import format_account_status


AgentToolHandler = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class AgentTool:
    """一个由插件明确注册、可独立审计的 Agent 工具。"""

    name: str
    description: str
    requires_confirmation: bool
    handler: AgentToolHandler


class AgentRuntime:
    """管理只读工具，并为后续确认式写操作保留统一入口。"""

    def __init__(self, tools: list[AgentTool]):
        self._tools = {tool.name: tool for tool in tools}

    def help_text(self) -> str:
        lines = ["智能体工具（仅超级用户）"]
        for tool in self._tools.values():
            confirmation = "需确认" if tool.requires_confirmation else "只读"
            lines.append(f"- {tool.name}：{tool.description}（{confirmation}）")
        lines.append("用法：智能体 工具 / 智能体 状态 / 智能体 模型")
        return "\n".join(lines)

    async def execute(self, name: str) -> str:
        normalized = name.strip()
        if normalized in {"", "帮助", "工具"}:
            return self.help_text()
        tool = self._tools.get(normalized)
        if tool is None:
            return "未找到该智能体工具。请先使用“智能体 工具”查看可用项。"
        if tool.requires_confirmation:
            return "该工具需要显式确认后才能执行，确认流程尚未配置。"
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


def create_agent_runtime(service: ChatService) -> AgentRuntime:
    """创建默认只读工具集，不触发远程能力刷新或任何账户操作。"""

    async def account_status() -> str:
        return format_account_status(await service.get_account_status())

    async def model_catalog() -> str:
        return _format_model_catalog(await service.get_model_catalog(fetch_remote=False))

    return AgentRuntime([
        AgentTool("状态", "查看账户与浏览器运行诊断", False, account_status),
        AgentTool("模型", "查看本地配置的模型别名", False, model_catalog),
    ])
