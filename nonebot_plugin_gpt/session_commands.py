"""逻辑会话的展示和切换辅助函数。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .chat_runtime import ChatRuntime
from .conversation import ConversationKey, ConversationState


_CHINA_TIMEZONE = timezone(timedelta(hours=8))


def _format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(_CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return "未知"


def format_sessions(sessions: list[ConversationState], active_logical_id: str) -> str:
    """生成适合所有适配器发送的紧凑逻辑会话列表。"""
    if not sessions:
        return "当前还没有可切换的逻辑会话。发送一条消息或初始化人设后会自动创建。"
    lines = ["逻辑会话（按最近使用排序）"]
    for index, state in enumerate(sessions, start=1):
        current = "当前" if state.logical_id == active_logical_id else "可切换"
        label = state.label or state.persona_name or "未命名会话"
        persona = state.persona_name or "无"
        lines.append(
            f"{index}. [{current}] {label}\n"
            f"   人设：{persona}｜模型：{state.model or 'auto'}｜检查点：{len(state.checkpoints)}\n"
            f"   创建：{_format_time(state.created_at)}｜更新：{_format_time(state.updated_at)}"
        )
    lines.append("使用“切换会话 序号”切换逻辑会话。")
    return "\n".join(lines)


async def list_sessions(runtime: ChatRuntime, key: ConversationKey) -> str:
    """获取当前会话范围内的逻辑会话展示文本。"""
    active = await runtime.get_active_session(key)
    return format_sessions(await runtime.list_sessions(key), active.logical_id)


async def switch_session(runtime: ChatRuntime, key: ConversationKey, value: str) -> str:
    """按用户可见序号切换逻辑会话。"""
    try:
        index = int(value.strip())
    except ValueError:
        return "请输入要切换的会话序号。"
    sessions = await runtime.list_sessions(key)
    if index < 1 or index > len(sessions):
        return f"会话序号应在 1 到 {len(sessions)} 之间。" if sessions else "当前没有可切换的会话。"
    state = await runtime.switch_session(key, sessions[index - 1].logical_id)
    return f"已切换到逻辑会话：{state.label or state.persona_name or '未命名会话'}。"
