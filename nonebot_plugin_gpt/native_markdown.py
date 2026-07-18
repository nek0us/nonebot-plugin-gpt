"""将常用 Markdown 投影为适配器可导出的 UniSeg 富文本。"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable

import markdown
from nonebot.adapters import Event
from nonebot_plugin_alconna.uniseg import Text, UniMessage


_VOID_TAGS = frozenset({"br", "hr", "img"})
_INLINE_STYLES = {
    "strong": "bold",
    "b": "bold",
    "em": "italic",
    "i": "italic",
    "del": "strikethrough",
    "s": "strikethrough",
    "code": "code",
}


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["_Node | str"] = field(default_factory=list)


class _MarkdownHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {key: value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)


def supports_native_markdown(event: Event) -> bool:
    """返回当前已验证可导出 UniSeg 文本样式的适配器能力。"""
    return event.__class__.__module__.startswith("nonebot.adapters.telegram.")


def _plain_text(children: Iterable[_Node | str]) -> str:
    result: list[str] = []
    for child in children:
        if isinstance(child, str):
            result.append(child)
        elif child.tag == "br":
            result.append("\n")
        elif child.tag == "img":
            result.append(child.attrs.get("alt") or child.attrs.get("src", ""))
        else:
            result.append(_plain_text(child.children))
    return "".join(result)


def _append_text(message: UniMessage, value: str, styles: tuple[str, ...] = ()) -> None:
    if not value:
        return
    segment = Text(value)
    if styles:
        segment.mark(0, len(value), *styles)
    # 不能使用 ``+=``：UniMessage 会合并相邻 Text，Telegram 导出器便无法
    # 同时保留不同文本样式与 URL 实体。
    message.append(segment)


def _render_inline(message: UniMessage, children: Iterable[_Node | str], styles: tuple[str, ...] = ()) -> None:
    for child in children:
        if isinstance(child, str):
            _append_text(message, child, styles)
            continue
        if child.tag == "br":
            _append_text(message, "\n", styles)
            continue
        if child.tag == "a":
            label = _plain_text(child.children).strip()
            url = child.attrs.get("href", "")
            if label and url:
                # UniMessage 会合并相邻 Text 并丢失 cover 子节点；保留标题，
                # 将 URL 单独标记为原生链接，Telegram 导出器可稳定生成 URL 实体。
                _append_text(message, f"{label} (")
                message.append(Text(url).link())
                _append_text(message, ")")
            else:
                _render_inline(message, child.children, styles)
            continue
        if child.tag == "img":
            _append_text(message, child.attrs.get("alt") or child.attrs.get("src", ""), styles)
            continue
        if child.tag in _INLINE_STYLES:
            _render_inline(message, child.children, styles + (_INLINE_STYLES[child.tag],))
            continue
        _render_inline(message, child.children, styles)


def _append_newlines(message: UniMessage, count: int = 2) -> None:
    _append_text(message, "\n" * count)


def _render_list(message: UniMessage, node: _Node, *, ordered: bool) -> None:
    index = 1
    for item in (child for child in node.children if isinstance(child, _Node) and child.tag == "li"):
        _append_text(message, f"{index}. " if ordered else "• ")
        _render_inline(message, item.children)
        _append_text(message, "\n")
        index += 1
    _append_text(message, "\n")


def _render_table(message: UniMessage, node: _Node) -> None:
    rows: list[_Node] = []

    def find_rows(children: Iterable[_Node | str]) -> None:
        for child in children:
            if isinstance(child, _Node):
                if child.tag == "tr":
                    rows.append(child)
                else:
                    find_rows(child.children)

    find_rows(node.children)
    for row in rows:
        cells = [
            _plain_text(cell.children).strip()
            for cell in row.children
            if isinstance(cell, _Node) and cell.tag in {"th", "td"}
        ]
        _append_text(message, " | ".join(cells))
        _append_text(message, "\n")
    _append_text(message, "\n")


def _render_blocks(message: UniMessage, children: Iterable[_Node | str]) -> None:
    for child in children:
        if isinstance(child, str):
            _append_text(message, child)
            continue
        if child.tag in {"p", "div"}:
            _render_inline(message, child.children)
            _append_newlines(message)
        elif child.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            _render_inline(message, child.children, ("bold",))
            _append_newlines(message)
        elif child.tag == "ul":
            _render_list(message, child, ordered=False)
        elif child.tag == "ol":
            _render_list(message, child, ordered=True)
        elif child.tag == "pre":
            value = _plain_text(child.children).strip("\n")
            _append_text(message, value, ("pre",))
            _append_newlines(message)
        elif child.tag == "blockquote":
            value = _plain_text(child.children).strip()
            _append_text(message, value, ("blockquote",))
            _append_newlines(message)
        elif child.tag == "table":
            _render_table(message, child)
        elif child.tag == "hr":
            _append_text(message, "────────")
            _append_newlines(message)
        else:
            _render_inline(message, child.children)


def markdown_to_unimessage(source: str) -> UniMessage:
    """将常见 Markdown 转为 Telegram 等适配器可识别的 UniSeg 文本样式。"""
    parser = _MarkdownHtmlParser()
    parser.feed(markdown.markdown(
        source,
        extensions=["pymdownx.tasklist", "tables", "fenced_code", "pymdownx.tilde"],
    ))
    parser.close()
    message = UniMessage()
    _render_blocks(message, parser.root.children)
    return message or UniMessage.text(source)
