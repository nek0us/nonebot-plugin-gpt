"""管理型长输出的 Markdown 分页与图片渲染。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .event_scope import strip_group_speaker_prompt
from .history_views import parse_history_range
from .image_fallback import render_markdown_page, use_local_font_renderer


def _split_block(block: str, limit: int) -> list[str]:
    """尽量按段落或换行拆分超长内容，避免在一行中间截断。"""
    normalized = block.strip()
    if len(normalized) <= limit:
        return [normalized] if normalized else []

    pieces = normalized.splitlines(keepends=True) or [normalized]
    result: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > limit:
            if current:
                result.append(current.strip())
                current = ""
            result.extend(piece[index : index + limit].strip() for index in range(0, len(piece), limit))
            continue
        if current and len(current) + len(piece) > limit:
            result.append(current.strip())
            current = piece
        else:
            current += piece
    if current.strip():
        result.append(current.strip())
    return result


def build_markdown_pages(
    title: str,
    blocks: Iterable[str],
    *,
    page_limit: int = 4200,
) -> tuple[str, ...]:
    """把语义块分页为独立可渲染的 Markdown 文档。"""
    heading = f"# {title}"
    payload_limit = max(page_limit - len(heading) - 48, 800)
    normalized_blocks: list[str] = []
    for block in blocks:
        normalized_blocks.extend(_split_block(str(block), payload_limit))
    if not normalized_blocks:
        normalized_blocks = ["暂无可展示内容。"]

    pages: list[list[str]] = [[]]
    current_length = 0
    for block in normalized_blocks:
        extra_length = len(block) + (2 if pages[-1] else 0)
        if pages[-1] and current_length + extra_length > payload_limit:
            pages.append([])
            current_length = 0
        pages[-1].append(block)
        current_length += len(block) + (2 if current_length else 0)

    total = len(pages)
    return tuple(
        f"{heading}\n\n" + "\n\n".join(page) + f"\n\n---\n第 {index} / {total} 页"
        for index, page in enumerate(pages, start=1)
    )


def markdown_pages_from_text(title: str, text: str, *, page_limit: int = 4200) -> tuple[str, ...]:
    """把既有管理文本按自然段转成图片文档页。"""
    blocks = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
    return build_markdown_pages(title, blocks, page_limit=page_limit)


def build_history_markdown_pages(
    history: Iterable[dict[str, str]],
    value: str = "",
    *,
    page_limit: int = 4200,
) -> tuple[str, ...]:
    """按问答轮次构造历史记录；异常长的单条内容会带续页标题拆分。"""
    entries = list(history)
    start, end = parse_history_range(value, len(entries))
    selected = entries[start:end]
    blocks: list[str] = []
    for index, item in enumerate(selected, start=start + 1):
        question = strip_group_speaker_prompt(str(item.get("Q") or item.get("input") or "")).strip()
        answer = str(item.get("A") or item.get("output") or "").strip()
        question = question or "（空消息）"
        answer = answer or "（无回复）"
        whole_round = f"## 第 {index} 轮\n\n### 用户\n\n{question}\n\n### 回复\n\n{answer}"
        if len(whole_round) <= page_limit - 180:
            blocks.append(whole_round)
            continue

        for part, content in (("用户", question), ("回复", answer)):
            segments = _split_block(content, max(page_limit - 260, 700))
            for segment_index, segment in enumerate(segments, start=1):
                continuation = "" if segment_index == 1 else "（续）"
                blocks.append(f"## 第 {index} 轮{continuation}\n\n### {part}\n\n{segment}")
    return build_markdown_pages("聊天记录", blocks, page_limit=page_limit)


async def render_markdown_pages(pages: Iterable[str]) -> tuple[bytes, ...]:
    """延迟导入 htmlkit，避免未启用图片能力时影响插件加载。"""
    page_list = tuple(pages)
    if use_local_font_renderer():
        return tuple(render_markdown_page(page) for page in page_list)

    from nonebot_plugin_htmlkit import md_to_pic

    images = []
    for page in page_list:
        images.append(await md_to_pic(page, dpi=120, max_width=860))
    return tuple(images)
