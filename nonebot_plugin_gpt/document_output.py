"""管理型长输出的 Markdown 分页与图片渲染。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape
from urllib.parse import urlparse

import markdown

from .event_scope import project_group_speaker_prompt
from .history_views import normalize_history_markdown, parse_history_range, replace_history_links
from .image_fallback import render_history_page, render_markdown_page, use_local_font_renderer


_HISTORY_STYLE = """
* { box-sizing: border-box; }
:root { --gpt-image-font-scale: {{ font_scale }}; }
body { margin: 0; color: #26334d; background: #f6f7fb; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
.sheet { width: 760px; padding: 22px; background: #f6f7fb; }
.header { padding: 24px 28px; border: 1px solid #e3e6f0; border-left: 7px solid #8c75d9; border-radius: 10px; background: #ffffff; }
h1 { margin: 0; color: #2c3654; font-size: calc(30px * var(--gpt-image-font-scale)); line-height: 1.25; }
.subtitle { margin: 8px 0 0; color: #737b91; font-size: calc(15px * var(--gpt-image-font-scale)); }
.round { margin-top: 20px; }
.round-label { display: inline-block; margin-bottom: 9px; padding: 6px 12px; color: #6149ad; border-radius: 999px; background: #eee9ff; font-size: calc(15px * var(--gpt-image-font-scale)); font-weight: 700; }
.card { padding: 16px 18px; border-radius: 10px; }
.card + .card { margin-top: 10px; }
.user { background: #eaf3ff; border: 1px solid #d4e8ff; }
.reply { background: #fff0f6; border: 1px solid #ffdce9; }
.role { margin: 0 0 9px; font-size: calc(15px * var(--gpt-image-font-scale)); font-weight: 700; }
.user .role { color: #2d6eae; }
.reply .role { color: #b4537c; }
.content { color: #29384f; font-size: calc(18px * var(--gpt-image-font-scale)); line-height: 1.74; white-space: pre-wrap; overflow-wrap: anywhere; }
.content.markdown { white-space: normal; }
.content.markdown > :first-child { margin-top: 0; }.content.markdown > :last-child { margin-bottom: 0; }
.content.markdown p { margin: 11px 0; white-space: pre-wrap; }
.content.markdown ul, .content.markdown ol { margin: 11px 0; padding-left: 1.55em; }
.content.markdown li { margin: 6px 0; }
.content.markdown li::marker { color: #b4537c; }
.content.markdown strong { color: #a34b72; }
.content.markdown hr { border: 0; border-top: 1px solid #e7c9d7; margin: 18px 0; }
.content.markdown blockquote { margin: 13px 0; padding: 9px 13px; color: #5d6179; border-left: 4px solid #edbdd0; background: #fff8fb; }
.content.markdown a { color: #4779ba; overflow-wrap: anywhere; }
.references { margin: 20px 0 0; padding: 14px 16px; color: #58627b; border: 1px solid #e0e4ee; border-radius: 9px; background: #ffffff; }
.references-title { margin: 0 0 8px; color: #5d4ca3; font-size: calc(15px * var(--gpt-image-font-scale)); font-weight: 700; }
.references ol { margin: 0; padding-left: 1.45em; }.references li { margin: 6px 0; font-size: calc(14px * var(--gpt-image-font-scale)); line-height: 1.55; }
.references .domain { color: #818aa0; }
.footer { margin: 18px 4px 0; color: #8991a4; font-size: 12px; text-align: right; }
"""


_DOCUMENT_STYLE = """
* { box-sizing: border-box; }
:root { --gpt-image-font-scale: {{ font_scale }}; }
body { margin: 0; color: #29384f; background: #f6f7fb; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
.sheet { width: 760px; padding: 22px; background: #f6f7fb; }
.document { padding: 24px 25px; border: 1px solid #e3e6f0; border-radius: 10px; background: #ffffff; }
.document > :first-child { margin-top: 0; }.document > :last-child { margin-bottom: 0; }
.document h1 { margin: 0 0 20px; padding-left: 14px; color: #354064; border-left: 6px solid #8c75d9; font-size: calc(30px * var(--gpt-image-font-scale)); line-height: 1.3; }
.document h2 { margin: 26px 0 14px; padding-left: 12px; color: #4d6695; border-left: 5px solid #79a9dc; font-size: calc(24px * var(--gpt-image-font-scale)); line-height: 1.35; }
.document h3 { margin: 21px 0 11px; padding-left: 10px; color: #a7547d; border-left: 4px solid #e58ab0; font-size: calc(20px * var(--gpt-image-font-scale)); line-height: 1.4; }
.document p, .document li { color: #3f4d66; font-size: calc(18px * var(--gpt-image-font-scale)); line-height: 1.74; }.document p { margin: 12px 0; }
.document ul, .document ol { margin: 12px 0; padding-left: 1.55em; }.document li { margin: 7px 0; }.document li::marker { color: #8c75d9; }
.document blockquote { margin: 16px 0; padding: 12px 16px; color: #5d6179; border-left: 4px solid #d6c8ff; border-radius: 0 8px 8px 0; background: #f6f2ff; }
.document code { padding: 2px 5px; color: #a34b72; border-radius: 4px; background: #fff1f6; font-family: Consolas, monospace; }
.document pre { margin: 16px 0; padding: 16px; overflow-x: auto; color: #edf2ff; border-radius: 8px; background: #30394f; }.document pre code { padding: 0; color: inherit; background: transparent; }
.document table { width: 100%; margin: 16px 0; border-collapse: separate; border-spacing: 0; overflow: hidden; border: 1px solid #e3e6f0; border-radius: 8px; font-size: calc(16px * var(--gpt-image-font-scale)); }.document th { padding: 10px 12px; color: #5b4d9b; background: #eef2ff; text-align: left; }.document td { padding: 10px 12px; color: #3f4d66; border-top: 1px solid #e9ecf2; }.document tr:nth-child(even) td { background: #fff9fc; }
.document a { color: #4779ba; text-decoration: none; overflow-wrap: anywhere; }.document img { display: block; max-width: 100%; height: auto; margin: 14px auto; border-radius: 8px; }.document hr { border: 0; border-top: 1px solid #e3e6ef; margin: 22px 0; }
"""


def build_document_html(markdown_text: str, *, font_scale: float = 1.0) -> str:
    """把管理文档渲染为与表格和历史一致的静态页面。"""
    content = markdown.markdown(
        markdown_text,
        extensions=["pymdownx.tasklist", "tables", "fenced_code", "codehilite", "pymdownx.tilde"],
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<style>{_DOCUMENT_STYLE.replace('{{ font_scale }}', f'{font_scale:.2f}')}</style></head><body><main class=\"sheet\">"
        f'<article class="document">{content}</article></main></body></html>'
    )


@dataclass(frozen=True)
class HistoryRound:
    number: int
    question: str
    answer: str
    speaker: str = "用户"
    continuation: str = ""
    link_indexes: tuple[int, ...] = ()


@dataclass(frozen=True)
class HistoryLink:
    index: int
    label: str
    url: str


@dataclass(frozen=True)
class HistoryPage:
    index: int
    total: int
    rounds: tuple[HistoryRound, ...]
    links: tuple[HistoryLink, ...]
    markdown: str
    html: str


class _HistoryLinkRegistry:
    def __init__(self) -> None:
        self._indexes: dict[tuple[str, str], int] = {}
        self.links: list[HistoryLink] = []

    def replace(self, value: str) -> tuple[str, tuple[int, ...]]:
        used: list[int] = []

        def resolve(label: str, url: str) -> str:
            key = (label, url)
            index = self._indexes.get(key)
            if index is None:
                index = len(self.links) + 1
                self._indexes[key] = index
                self.links.append(HistoryLink(index=index, label=label, url=url))
            if index not in used:
                used.append(index)
            return f"{label}[{index}]"

        return replace_history_links(value, resolve), tuple(used)


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
    anonymize: bool = False,
    reverse_order: bool = False,
    page_limit: int = 6000,
) -> tuple[str, ...]:
    """保留历史 Markdown 投影，供文本回退与兼容调用使用。"""
    return tuple(
        page.markdown
        for page in build_history_pages(
            history,
            value,
            anonymize=anonymize,
            reverse_order=reverse_order,
            page_limit=page_limit,
        )
    )


def _history_rounds(
    history: Iterable[dict[str, str]],
    value: str,
    *,
    anonymize: bool,
    reverse_order: bool,
    page_limit: int,
) -> tuple[list[HistoryRound], tuple[HistoryLink, ...]]:
    """将历史拆成可独立绘制的轮次，极长内容保留明确的续页标签。"""
    entries = list(history)
    start, end = parse_history_range(value, len(entries))
    selected = entries[start:end]
    numbered_entries = list(enumerate(selected, start=start + 1))
    if reverse_order:
        numbered_entries.reverse()
    rounds: list[HistoryRound] = []
    link_registry = _HistoryLinkRegistry()
    part_limit = max(page_limit - 560, 180)
    for index, item in numbered_entries:
        speaker, question = project_group_speaker_prompt(
            str(item.get("Q") or item.get("input") or ""),
            anonymize=anonymize,
        )
        question = normalize_history_markdown(question).strip()
        answer, link_indexes = link_registry.replace(
            str(item.get("A") or item.get("output") or "")
        )
        answer = answer.strip()
        question = question or "（空消息）"
        answer = answer or "（无回复）"
        if len(question) + len(answer) <= part_limit:
            rounds.append(
                HistoryRound(
                    index,
                    question,
                    answer,
                    speaker=speaker,
                    link_indexes=link_indexes,
                )
            )
            continue

        for is_question, role, content in ((True, speaker, question), (False, "回复", answer)):
            segments = _split_block(content, max(part_limit - 180, 120))
            for segment_index, segment in enumerate(segments, start=1):
                continuation = f"{role}续 {segment_index}/{len(segments)}" if len(segments) > 1 else role
                rounds.append(
                    HistoryRound(
                        index,
                        segment if is_question else "",
                        segment if not is_question else "",
                        speaker=speaker,
                        continuation=continuation,
                        link_indexes=tuple(
                            link_index
                            for link_index in link_indexes
                            if f"[{link_index}]" in segment
                        ),
                    )
                )
    return rounds, tuple(link_registry.links)


def _history_markdown(
    rounds: Iterable[HistoryRound],
    index: int,
    total: int,
    links: Iterable[HistoryLink] = (),
) -> str:
    blocks = ["# 聊天记录"]
    for round_item in rounds:
        label = f"第 {round_item.number} 轮"
        if round_item.continuation:
            label += f" · {round_item.continuation}"
        content = [f"## {label}"]
        if round_item.question:
            content.append(f"### {round_item.speaker}\n\n{round_item.question}")
        if round_item.answer:
            content.append(f"### 回复\n\n{round_item.answer}")
        blocks.append("\n\n".join(content))
    reference_links = tuple(links)
    if reference_links:
        blocks.append(
            "### 参考链接\n\n" + "\n".join(
                f"[{link.index}] {link.label} ({urlparse(link.url).netloc or link.url})"
                for link in reference_links
            )
        )
    blocks.append(f"---\n第 {index} / {total} 页")
    return "\n\n".join(blocks)


def _history_html(
    rounds: Iterable[HistoryRound],
    index: int,
    total: int,
    *,
    font_scale: float,
    links: Iterable[HistoryLink] = (),
) -> str:
    def answer_html(value: str) -> str:
        return markdown.markdown(
            escape(value),
            extensions=["pymdownx.tasklist", "tables", "fenced_code", "codehilite", "pymdownx.tilde"],
        )

    sections = []
    for round_item in rounds:
        label = f"第 {round_item.number} 轮"
        if round_item.continuation:
            label += f" · {round_item.continuation}"
        cards = []
        if round_item.question:
            cards.append(
                f'<section class="card user"><p class="role">{escape(round_item.speaker)}</p><div class="content">'
                f"{escape(round_item.question)}</div></section>"
            )
        if round_item.answer:
            cards.append(
                f'<section class="card reply"><p class="role">回复</p><div class="content markdown">'
                f"{answer_html(round_item.answer)}</div></section>"
            )
        sections.append(f'<section class="round"><div class="round-label">{escape(label)}</div>{"".join(cards)}</section>')
    reference_links = tuple(links)
    references = ""
    if reference_links:
        items = "".join(
            f'<li><span>[{link.index}] {escape(link.label)}</span> '
            f'<span class="domain">{escape(urlparse(link.url).netloc or link.url)}</span></li>'
            for link in reference_links
        )
        references = f'<section class="references"><p class="references-title">参考链接</p><ol>{items}</ol></section>'
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<style>{_HISTORY_STYLE.replace('{{ font_scale }}', f'{font_scale:.2f}')}</style></head><body><main class=\"sheet\">"
        '<header class="header"><h1>聊天记录</h1><p class="subtitle">当前逻辑会话的已保存对话</p></header>'
        f"{''.join(sections)}{references}<footer class=\"footer\">第 {index} / {total} 页</footer>"
        "</main></body></html>"
    )


def build_history_pages(
    history: Iterable[dict[str, str]],
    value: str = "",
    *,
    anonymize: bool = False,
    reverse_order: bool = False,
    page_limit: int = 6000,
    font_scale: float = 1.0,
) -> tuple[HistoryPage, ...]:
    """构造适合图片卡片展示的聊天历史分页。"""
    rounds, links = _history_rounds(
        history,
        value,
        anonymize=anonymize,
        reverse_order=reverse_order,
        page_limit=page_limit,
    )
    if not rounds:
        rounds = [HistoryRound(0, "当前逻辑会话还没有可展示的聊天记录。", "")]

    pages: list[list[HistoryRound]] = [[]]
    current_length = 0
    for round_item in rounds:
        size = len(round_item.question) + len(round_item.answer) + len(round_item.continuation) + 120
        if pages[-1] and current_length + size > page_limit:
            pages.append([])
            current_length = 0
        pages[-1].append(round_item)
        current_length += size

    total = len(pages)
    result: list[HistoryPage] = []
    for index, page_rounds in enumerate(pages, start=1):
        page_link_indexes = {
            link_index
            for round_item in page_rounds
            for link_index in round_item.link_indexes
        }
        page_links = tuple(link for link in links if link.index in page_link_indexes)
        result.append(
            HistoryPage(
                index=index,
                total=total,
                rounds=tuple(page_rounds),
                links=page_links,
                markdown=_history_markdown(page_rounds, index, total, page_links),
                html=_history_html(
                    page_rounds,
                    index,
                    total,
                    font_scale=font_scale,
                    links=page_links,
                ),
            )
        )
    return tuple(result)


def history_reference_text(pages: Iterable[HistoryPage]) -> str:
    """生成图片后补发的可复制链接清单。"""
    links: dict[int, HistoryLink] = {}
    for page in pages:
        for link in page.links:
            links.setdefault(link.index, link)
    if not links:
        return ""
    return "参考链接\n" + "\n".join(
        f"[{link.index}] {link.label}\n{link.url}"
        for link in links.values()
    )


async def render_markdown_pages(
    pages: Iterable[str],
    *,
    font_scale: float = 1.0,
) -> tuple[bytes, ...]:
    """延迟导入 htmlkit，避免未启用图片能力时影响插件加载。"""
    page_list = tuple(pages)
    if use_local_font_renderer():
        return tuple(render_markdown_page(page, font_scale=font_scale) for page in page_list)

    from nonebot_plugin_htmlkit import html_to_pic

    images = []
    for page in page_list:
        images.append(await html_to_pic(
            build_document_html(page, font_scale=font_scale),
            dpi=110,
            max_width=800,
            device_height=10,
            default_font_size=17,
        ))
    return tuple(images)


async def render_history_pages(
    pages: Iterable[HistoryPage],
    *,
    font_scale: float = 1.0,
) -> tuple[bytes, ...]:
    """渲染带角色色彩的聊天历史卡片。"""
    page_list = tuple(pages)
    if use_local_font_renderer():
        return tuple(render_history_page(page, font_scale=font_scale) for page in page_list)

    from nonebot_plugin_htmlkit import html_to_pic

    return tuple(
        await html_to_pic(page.html, dpi=110, max_width=800, device_height=10, default_font_size=17)
        for page in page_list
    )
