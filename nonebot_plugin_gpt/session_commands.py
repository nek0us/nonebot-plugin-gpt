"""逻辑会话的展示和切换辅助函数。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .chat_runtime import ChatRuntime
from .conversation import ConversationKey, ConversationState


_CHINA_TIMEZONE = timezone(timedelta(hours=8))


def format_session_time(value: Any) -> str:
    if value in (None, ""):
        return "未知"
    try:
        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            text = str(value).strip()
            parsed = (
                datetime.fromtimestamp(float(text), timezone.utc)
                if text.replace(".", "", 1).isdigit()
                else datetime.fromisoformat(text.replace("Z", "+00:00"))
            )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(_CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, TypeError, ValueError):
        return "未知"


def session_creator_display(state: ConversationState) -> str:
    name = " ".join(str(state.creator_name or "").split())
    user_id = str(state.creator_id or "").strip()
    if name and user_id:
        return f"{name}（{user_id}）"
    return name or user_id or "未知"


def session_title_display(state: ConversationState) -> str:
    return (
        state.original_title
        or state.label
        or state.persona_name
        or "未命名会话"
    )


def session_detail_display(state: ConversationState) -> str:
    local_title = state.label or state.persona_name or "未命名会话"
    original_title = state.original_title or "尚未同步"
    persona = state.persona_name or "无"
    return (
        f"网页原始标题：{original_title}\n"
        f"本地首句标题：{local_title}\n"
        f"人设：{persona}｜模型：{state.model or 'auto'}｜"
        f"检查点：{len(state.checkpoints)}"
    )


def session_time_display(state: ConversationState) -> str:
    lines = [
        f"创建：{format_session_time(state.created_at)}",
        f"更新：{format_session_time(state.updated_at)}",
    ]
    upstream_created_at = state.metadata.get("upstream_created_at")
    if upstream_created_at not in (None, ""):
        lines.append(f"网页创建：{format_session_time(upstream_created_at)}")
    return "\n".join(lines)


def format_sessions(sessions: list[ConversationState], active_logical_id: str) -> str:
    """生成适合所有适配器发送的紧凑逻辑会话列表。"""
    if not sessions:
        return "当前还没有可切换的逻辑会话。发送一条消息或初始化人设后会自动创建。"
    lines = ["历史会话（按最近使用排序）"]
    for index, state in enumerate(sessions, start=1):
        current = "当前" if state.logical_id == active_logical_id else "可切换"
        lines.append(
            f"{index}. [{current}] {session_title_display(state)}\n"
            f"   创建者：{session_creator_display(state)}\n"
            f"   {session_detail_display(state).replace(chr(10), chr(10) + '   ')}\n"
            f"   {session_time_display(state).replace(chr(10), chr(10) + '   ')}"
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
