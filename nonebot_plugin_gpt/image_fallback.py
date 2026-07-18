"""本地 CJK 字体可用时的跨平台中文图片渲染。"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from .history_views import history_plain_text


def use_local_font_renderer() -> bool:
    return any(path.exists() for path in _font_candidates())


def _font_candidates() -> tuple[Path, ...]:
    if sys.platform != "win32":
        return (
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        )
    return (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    )


def _bold_font_candidates() -> tuple[Path, ...]:
    if sys.platform == "win32":
        return (Path("C:/Windows/Fonts/msyhbd.ttc"),) + _font_candidates()
    return _font_candidates()


@lru_cache(maxsize=12)
def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    for path in (_bold_font_candidates() if bold else _font_candidates()):
        if path.exists():
            return ImageFont.truetype(path, size=size)
    raise RuntimeError("未找到可用的中文字体")


def _wrap(draw: Any, text: str, font: Any, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if not raw_line:
            lines.append("")
            continue
        current = ""
        for char in raw_line:
            candidate = current + char
            if current and draw.textlength(candidate, font=font) > width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines or [""]


def _scaled_size(size: int, font_scale: float) -> int:
    return max(10, round(size * font_scale))


def render_markdown_page(markdown: str, *, font_scale: float = 1.0) -> bytes:
    """以基础 Markdown 层级渲染一页中文文档。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width = 820
    margin = 34
    content_width = width - margin * 2
    probe = Image.new("RGB", (width, 10), "white")
    draw = ImageDraw.Draw(probe)
    source_lines = str(markdown).splitlines()
    title = "管理文档"
    if source_lines and source_lines[0].startswith("# "):
        title = source_lines.pop(0)[2:].strip() or title
    rendered: list[tuple[str, Any, str, int]] = []
    for raw in source_lines:
        stripped = raw.strip()
        if stripped.startswith("### "):
            font, color, gap, text = _font(_scaled_size(22, font_scale), bold=True), "#1d2939", 10, stripped[4:]
        elif stripped.startswith("## "):
            font, color, gap, text = _font(_scaled_size(26, font_scale), bold=True), "#5d4aa3", 16, stripped[3:]
        elif stripped == "---":
            font, color, gap, text = _font(_scaled_size(15, font_scale)), "#829ab1", 12, ""
        else:
            font, color, gap, text = _font(_scaled_size(19, font_scale)), "#243b53", 9, raw
        for line in _wrap(draw, text, font, content_width):
            rendered.append((line, font, color, gap))

    header_height = 122
    height = header_height + margin + sum(font.size + gap for _, font, _, gap in rendered) + margin
    image = Image.new("RGB", (width, max(height, 240)), "#f6f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((margin, 20, width - margin, header_height), radius=14, fill="#ffffff", outline="#e3e6f0")
    draw.rounded_rectangle((margin + 18, 43, margin + 24, 98), radius=3, fill="#8c75d9")
    draw.text((margin + 38, 41), title, font=_font(_scaled_size(29, font_scale), bold=True), fill="#2c3654")
    y = header_height + 28
    for line, font, color, gap in rendered:
        if not line and color == "#829ab1":
            draw.line((margin, y + 4, width - margin, y + 4), fill="#d9e2ec", width=2)
        elif line:
            draw.text((margin, y), line, font=font, fill=color)
        y += font.size + gap
    result = BytesIO()
    image.save(result, format="PNG", optimize=True)
    return result.getvalue()


def render_history_page(page: Any, *, font_scale: float = 1.0) -> bytes:
    """将聊天历史绘制为区分用户与回复的柔和色彩卡片。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width = 820
    margin = 34
    content_width = width - margin * 2
    probe = Image.new("RGB", (width, 10), "white")
    probe_draw = ImageDraw.Draw(probe)
    title_font = _font(_scaled_size(29, font_scale), bold=True)
    round_font = _font(_scaled_size(18, font_scale), bold=True)
    role_font = _font(_scaled_size(17, font_scale), bold=True)
    body_font = _font(_scaled_size(19, font_scale))
    reference_font = _font(_scaled_size(15, font_scale))
    line_height = body_font.size + 10
    prepared: list[tuple[Any, list[str], list[str]]] = []
    content_height = 0
    for round_item in page.rounds:
        user_lines = _wrap(probe_draw, history_plain_text(str(round_item.question)), body_font, content_width - 52) if round_item.question else []
        reply_lines = _wrap(probe_draw, history_plain_text(str(round_item.answer)), body_font, content_width - 52) if round_item.answer else []
        prepared.append((round_item, user_lines, reply_lines))
        content_height += 47
        if user_lines:
            content_height += 50 + len(user_lines) * line_height
        if reply_lines:
            content_height += 50 + len(reply_lines) * line_height
        content_height += 16

    reference_lines: list[str] = []
    for link in getattr(page, "links", ()):
        domain = link.url.split("/", maxsplit=3)[2] if "://" in link.url else link.url
        reference_lines.extend(
            _wrap(
                probe_draw,
                f"[{link.index}] {link.label} · {domain}",
                reference_font,
                content_width - 52,
            )
        )
    if reference_lines:
        content_height += 48 + len(reference_lines) * (reference_font.size + 8) + 10

    header_height = 126
    height = header_height + content_height + margin
    image = Image.new("RGB", (width, max(height, 260)), "#f6f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((margin, 20, width - margin, 112), radius=14, fill="#ffffff", outline="#e3e6f0")
    draw.rounded_rectangle((margin + 18, 43, margin + 24, 96), radius=3, fill="#8c75d9")
    draw.text((margin + 38, 38), "聊天记录", font=title_font, fill="#2c3654")
    draw.text((margin + 38, 78), "当前逻辑会话的已保存对话", font=_font(_scaled_size(15, font_scale)), fill="#737b91")

    y = header_height
    for round_item, user_lines, reply_lines in prepared:
        label = "当前状态" if round_item.number == 0 else f"第 {round_item.number} 轮"
        if round_item.continuation:
            label += f" · {round_item.continuation}"
        label_width = int(draw.textlength(label, font=round_font)) + 28
        draw.rounded_rectangle((margin, y, margin + label_width, y + 35), radius=17, fill="#eee9ff")
        draw.text((margin + 14, y + 7), label, font=round_font, fill="#6149ad")
        y += 47
        for role, lines, fill, border, role_color in (
            (round_item.speaker, user_lines, "#eaf3ff", "#d4e8ff", "#2d6eae"),
            ("回复", reply_lines, "#fff0f6", "#ffdce9", "#b4537c"),
        ):
            if not lines:
                continue
            card_height = 48 + len(lines) * line_height
            draw.rounded_rectangle((margin, y, width - margin, y + card_height), radius=12, fill=fill, outline=border)
            draw.text((margin + 18, y + 13), role, font=role_font, fill=role_color)
            text_y = y + 42
            for line in lines:
                draw.text((margin + 18, text_y), line, font=body_font, fill="#29384f")
                text_y += line_height
            y += card_height + 10
        y += 6

    if reference_lines:
        reference_height = 43 + len(reference_lines) * (reference_font.size + 8)
        draw.rounded_rectangle(
            (margin, y, width - margin, y + reference_height),
            radius=12,
            fill="#ffffff",
            outline="#e0e4ee",
        )
        draw.text((margin + 18, y + 12), "参考链接", font=role_font, fill="#5d4ca3")
        text_y = y + 39
        for line in reference_lines:
            draw.text((margin + 18, text_y), line, font=reference_font, fill="#58627b")
            text_y += reference_font.size + 8
        y += reference_height + 10

    footer = f"第 {page.index} / {page.total} 页"
    footer_font = _font(_scaled_size(15, font_scale))
    draw.text((width - margin - int(draw.textlength(footer, font=footer_font)), y + 5), footer, font=footer_font, fill="#8991a4")
    result = BytesIO()
    image.save(result, format="PNG", optimize=True)
    return result.getvalue()


def render_table_page(page: Any, *, font_scale: float = 1.0) -> bytes:
    """用系统中文字体渲染结构化表格，避免 Windows Fontconfig 缺失。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width = 920
    margin = 32
    content_width = width - margin * 2
    probe = Image.new("RGB", (width, 10), "white")
    probe_draw = ImageDraw.Draw(probe)
    columns = tuple(page.columns)
    rows = tuple(page.rows)
    weights = []
    for index, column in enumerate(columns):
        longest = max([len(str(column))] + [len(str(row[index])) for row in rows if index < len(row)])
        weights.append(max(1.0, min(3.0, longest / 10)))
    total_weight = sum(weights) or 1
    widths = [int(content_width * weight / total_weight) for weight in weights]
    widths[-1] += content_width - sum(widths)
    body_font = _font(_scaled_size(17, font_scale))
    header_font = _font(_scaled_size(16, font_scale), bold=True)
    line_height = body_font.size + 9
    cell_lines = [
        [_wrap(probe_draw, str(value), body_font, max(widths[index] - 22, 40)) for index, value in enumerate(row)]
        for row in rows
    ]
    row_heights = [max((len(lines) for lines in row), default=1) * line_height + 20 for row in cell_lines]
    header_height = 126
    table_header_height = 46
    height = header_height + table_header_height + sum(row_heights) + 58
    image = Image.new("RGB", (width, max(height, 260)), "#f6f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((margin, 20, width - margin, header_height - 12), radius=14, fill="#ffffff", outline="#e3e6f0")
    draw.rounded_rectangle((margin + 18, 44, margin + 24, 99), radius=3, fill="#8c75d9")
    draw.text((margin + 38, 38), str(page.title), font=_font(_scaled_size(29, font_scale), bold=True), fill="#2c3654")
    draw.text((margin + 38, 78), str(page.subtitle), font=_font(_scaled_size(15, font_scale)), fill="#737b91")

    y = header_height
    draw.rectangle((margin, y, width - margin, y + table_header_height), fill="#eef2ff")
    x = margin
    for index, column in enumerate(columns):
        draw.text((x + 11, y + 12), str(column), font=header_font, fill="#5b4d9b")
        x += widths[index]
    y += table_header_height
    for row_index, (row, cells, row_height) in enumerate(zip(rows, cell_lines, row_heights)):
        draw.rectangle((margin, y, width - margin, y + row_height), fill="#ffffff" if row_index % 2 == 0 else "#fff9fc")
        draw.line((margin, y + row_height, width - margin, y + row_height), fill="#e3e6f0")
        x = margin
        for index, lines in enumerate(cells):
            for line_index, line in enumerate(lines):
                draw.text((x + 11, y + 10 + line_index * line_height), line, font=body_font, fill="#29384f")
            x += widths[index]
        y += row_height
    draw.text((width - margin - 120, y + 18), f"第 {page.index} / {page.total} 页", font=_font(_scaled_size(15, font_scale)), fill="#8991a4")
    result = BytesIO()
    image.save(result, format="PNG", optimize=True)
    return result.getvalue()
