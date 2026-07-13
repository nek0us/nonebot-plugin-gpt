"""逻辑会话历史记录的跨平台文本投影。"""

from __future__ import annotations

from collections.abc import Iterable

from .conversation import ConversationState


def parse_history_range(value: str, total: int) -> tuple[int, int]:
    """把命令参数解析为从一开始的半开区间。"""
    normalized = value.strip().replace(":", "-", 1)
    if not normalized:
        return 0, total
    try:
        if "-" in normalized:
            start_text, end_text = normalized.split("-", maxsplit=1)
            start = max(int(start_text or "1"), 1)
            end = min(int(end_text or str(total)), total)
            return start - 1, max(start - 1, end)
        index = max(int(normalized), 1)
        return index - 1, min(index, total)
    except ValueError:
        return 0, total


def format_history(history: Iterable[dict[str, str]], value: str = "") -> str:
    """生成不包含物理消息标识的问答历史文本。"""
    entries = list(history)
    start, end = parse_history_range(value, len(entries))
    selected = entries[start:end]
    if not selected:
        return "当前逻辑会话还没有可展示的聊天记录。"
    lines = ["聊天记录"]
    for index, item in enumerate(selected, start=start + 1):
        question = str(item.get("Q") or item.get("input") or "")
        answer = str(item.get("A") or item.get("output") or "")
        lines.extend((f"{index}. 用户：{question}", f"   回复：{answer}"))
    return "\n".join(lines)


def format_history_tree(state: ConversationState, history_count: int) -> str:
    """概览逻辑会话及自动压缩生成的检查点。"""
    label = state.label or state.persona_name or "未命名会话"
    lines = [
        f"逻辑会话：{label}",
        f"人设：{state.persona_name or '无'}",
        f"当前检查点消息数：{history_count}",
        f"自动压缩次数：{len(state.checkpoints)}",
    ]
    for index, checkpoint in enumerate(state.checkpoints, start=1):
        lines.append(f"检查点 {index}：模型 {checkpoint.model or 'auto'}，创建于 {checkpoint.created_at}")
    return "\n".join(lines)
