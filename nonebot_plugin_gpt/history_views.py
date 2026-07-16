"""逻辑会话历史记录的跨平台文本投影。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .event_scope import strip_group_speaker_prompt


@dataclass(frozen=True)
class HistoryProjection:
    """用户可见的历史记录及其到上游记录的索引映射。"""

    entries: tuple[dict[str, str], ...]
    source_indexes: tuple[int, ...]

    def resolve_rewind_reference(self, reference: str) -> str:
        """将可见轮次转换为核心库所需的原始一开始索引。"""
        normalized = reference.strip()
        if not normalized.isdecimal():
            return normalized

        visible_index = int(normalized)
        if visible_index < 1 or visible_index > len(self.source_indexes):
            raise ValueError(f"历史中没有第 {visible_index} 轮对话")
        # 核心库的 back_chat_from_input 使用从 1 开始的原始轮次。
        return str(self.source_indexes[visible_index - 1] + 1)


def project_history(
    history: Iterable[dict[str, str]],
    *,
    persona_prompt: str = "",
    hide_initial: bool = False,
) -> HistoryProjection:
    """隐藏人设初始化内容，并保留可见轮次到原始轮次的映射。"""
    entries: list[dict[str, str]] = []
    source_indexes: list[int] = []
    normalized_prompt = persona_prompt.strip()
    for index, item in enumerate(history):
        question = str(item.get("Q") or item.get("input") or "").strip()
        # 人设会作为物理会话首轮发送；强化人设或自动摘要重启时，正文
        # 也可能再次出现在后续轮次中，因此不能只依赖固定的第一轮。
        is_private_setup = (hide_initial and index == 0) or (
            bool(normalized_prompt) and normalized_prompt in question
        )
        if is_private_setup:
            continue
        entries.append(item)
        source_indexes.append(index)
    return HistoryProjection(tuple(entries), tuple(source_indexes))


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
        question = strip_group_speaker_prompt(str(item.get("Q") or item.get("input") or ""))
        answer = str(item.get("A") or item.get("output") or "")
        lines.extend((f"{index}. 用户：{question}", f"   回复：{answer}"))
    return "\n".join(lines)
