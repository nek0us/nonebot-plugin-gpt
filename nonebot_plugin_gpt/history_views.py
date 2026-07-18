"""逻辑会话历史记录的跨平台文本投影。"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .event_scope import project_group_speaker_prompt


_UPSTREAM_MARKUP = re.compile("\\ue200(?P<body>.*?)\\ue201", re.DOTALL)
_MARKDOWN_LINK = re.compile(r"(?<!!)\[(?P<label>[^\]]+)\]\((?P<url>[^\s)]+)(?:\s+['\"][^)]*['\"])?\)")
_MARKDOWN_EMPHASIS = re.compile(r"(?<!\\)(?:\*\*|__)(?P<value>.+?)(?<!\\)(?:\*\*|__)")
_MARKDOWN_CODE = re.compile(r"`(?P<value>[^`]+)`")
_AGENT_PROTOCOL_MARKER = "【ChatGPTWeb Agent Protocol】"
_AGENT_PRESENTATION_MARKER = "【已完成的受控任务】"
_AGENT_PRESENTATION_TASK = re.compile(
    r"(?:^|\n)用户原任务：(?P<task>.*?)(?=\n完成结果：|\Z)",
    re.DOTALL,
)


def _agent_presentation_task(value: str) -> str:
    """从人设化 Agent 结果的内部提示中恢复用户最初提出的任务。"""
    if _AGENT_PRESENTATION_MARKER not in value:
        return ""
    match = _AGENT_PRESENTATION_TASK.search(value)
    return match.group("task").strip().lstrip("，,：:").strip() if match else ""


def normalize_history_markdown(value: str) -> str:
    """移除网页私有富结构标记，保留可独立展示的 Markdown 正文。"""
    def replace_markup(match: re.Match[str]) -> str:
        parts = match.group("body").split("\ue202")
        if len(parts) >= 2 and parts[0] == "url":
            return parts[1]
        # cite、genui 等结构依赖网页响应元数据；历史文件未持久化该映射，不能伪造链接。
        return ""

    normalized = _UPSTREAM_MARKUP.sub(replace_markup, str(value or ""))
    return normalized.replace("\ue200", "").replace("\ue201", "").replace("\ue202", "")


def replace_history_links(value: str, resolve: Callable[[str, str], str]) -> str:
    """以调用方定义的文本替换普通 Markdown 链接。"""
    return _MARKDOWN_LINK.sub(
        lambda match: resolve(match.group("label").strip(), match.group("url").strip()),
        normalize_history_markdown(value),
    )


def history_plain_text(value: str) -> str:
    """为文本回退与本地字体渲染生成没有网页标记的可读内容。"""
    text = normalize_history_markdown(value)
    text = _MARKDOWN_LINK.sub(lambda match: f"{match.group('label')} ({match.group('url')})", text)
    text = _MARKDOWN_EMPHASIS.sub(lambda match: match.group("value"), text)
    text = _MARKDOWN_CODE.sub(lambda match: match.group("value"), text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*---+\s*$", "────────", text)
    return text


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
        presentation_task = _agent_presentation_task(question)
        # 人设会作为物理会话首轮发送；强化人设或自动摘要重启时，正文
        # 也可能再次出现在后续轮次中，因此不能只依赖固定的第一轮。
        is_private_setup = (hide_initial and index == 0) or (
            bool(normalized_prompt) and normalized_prompt in question
        )
        # 智能体决策协议会作为同一 ChatGPT 会话中的内部消息存在；展示给
        # 群成员既破坏人设，也可能泄露工具描述，因此和私有人设一并隐藏。
        if is_private_setup or _AGENT_PROTOCOL_MARKER in question:
            continue
        if presentation_task:
            # 角色化最终答复必须作为原聊天会话的一轮继续，才能继承人设和
            # 上下文；这里仅在展示层还原用户任务，避免暴露内部控制提示。
            visible_item = dict(item)
            if "Q" in visible_item or "input" not in visible_item:
                visible_item["Q"] = presentation_task
            else:
                visible_item["input"] = presentation_task
            entries.append(visible_item)
        else:
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


def parse_history_view_argument(value: str) -> tuple[str, bool]:
    """分离历史范围和展示顺序；“倒序”只影响显示，不改变轮次编号。"""
    normalized = value.strip()
    reverse_order = False
    for marker in ("倒序", "reverse", "desc"):
        index = normalized.lower().find(marker)
        if index >= 0:
            normalized = normalized[:index] + normalized[index + len(marker):]
            reverse_order = True
    return normalized.strip(), reverse_order


def format_history(
    history: Iterable[dict[str, str]],
    value: str = "",
    *,
    anonymize: bool = False,
    reverse_order: bool = False,
) -> str:
    """生成不包含物理消息标识的问答历史文本。"""
    entries = list(history)
    start, end = parse_history_range(value, len(entries))
    selected = entries[start:end]
    if not selected:
        return "当前逻辑会话还没有可展示的聊天记录。"
    lines = ["聊天记录"]
    numbered_entries = list(enumerate(selected, start=start + 1))
    if reverse_order:
        numbered_entries.reverse()
    for index, item in numbered_entries:
        speaker, question = project_group_speaker_prompt(
            str(item.get("Q") or item.get("input") or ""),
            anonymize=anonymize,
        )
        lines.extend((
            f"{index}. {speaker}：{history_plain_text(question)}",
            f"   回复：{history_plain_text(str(item.get('A') or item.get('output') or ''))}",
        ))
    return "\n".join(lines)
