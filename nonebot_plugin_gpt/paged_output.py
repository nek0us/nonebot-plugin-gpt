"""跨适配器管理文本的安全分页。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextPages:
    """需要逐页发送的纯文本输出。"""

    pages: tuple[str, ...]


def paginate_text(text: str, *, limit: int = 1500) -> TextPages:
    """按自然换行切分过长管理输出，避免平台单条消息上限。"""
    normalized = str(text or "").strip()
    if not normalized:
        return TextPages(("暂无可展示内容。",))
    if len(normalized) <= limit:
        return TextPages((normalized,))

    pages: list[str] = []
    remaining = normalized
    while len(remaining) > limit:
        boundary = remaining.rfind("\n", 0, limit + 1)
        if boundary <= 0:
            boundary = remaining.rfind("。", 0, limit + 1)
        if boundary <= 0:
            boundary = limit
        else:
            boundary += 1
        pages.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].lstrip("\n")
    if remaining:
        pages.append(remaining)

    if len(pages) == 1:
        return TextPages((pages[0],))
    total = len(pages)
    return TextPages(tuple(f"{page}\n\n[{index}/{total}]" for index, page in enumerate(pages, start=1)))
