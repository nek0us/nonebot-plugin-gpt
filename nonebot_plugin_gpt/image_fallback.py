"""本地 CJK 字体可用时的跨平台中文图片渲染。"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


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


def render_markdown_page(markdown: str) -> bytes:
    """以基础 Markdown 层级渲染一页中文文档。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width = 1104
    margin = 44
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
            font, color, gap, text = _font(20, bold=True), "#1d2939", 9, stripped[4:]
        elif stripped.startswith("## "):
            font, color, gap, text = _font(24, bold=True), "#12344d", 15, stripped[3:]
        elif stripped == "---":
            font, color, gap, text = _font(14), "#829ab1", 12, ""
        else:
            font, color, gap, text = _font(17), "#243b53", 7, raw
        for line in _wrap(draw, text, font, content_width):
            rendered.append((line, font, color, gap))

    header_height = 115
    height = header_height + margin + sum(font.size + gap for _, font, _, gap in rendered) + margin
    image = Image.new("RGB", (width, max(height, 220)), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width, header_height), radius=12, fill="#12344d")
    draw.text((margin, 24), "NONEBOT PLUGIN", font=_font(14, bold=True), fill="#b7d9d6")
    draw.text((margin, 50), title, font=_font(31, bold=True), fill="#ffffff")
    y = header_height + 25
    for line, font, color, gap in rendered:
        if not line and color == "#829ab1":
            draw.line((margin, y + 4, width - margin, y + 4), fill="#d9e2ec", width=2)
        elif line:
            draw.text((margin, y), line, font=font, fill=color)
        y += font.size + gap
    result = BytesIO()
    image.save(result, format="PNG", optimize=True)
    return result.getvalue()


def render_table_page(page: Any) -> bytes:
    """用系统中文字体渲染结构化表格，避免 Windows Fontconfig 缺失。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width = 1104
    margin = 38
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
    body_font = _font(16)
    header_font = _font(15, bold=True)
    cell_lines = [
        [_wrap(probe_draw, str(value), body_font, max(widths[index] - 22, 40)) for index, value in enumerate(row)]
        for row in rows
    ]
    row_heights = [max((len(lines) for lines in row), default=1) * 25 + 20 for row in cell_lines]
    header_height = 124
    table_header_height = 44
    height = header_height + table_header_height + sum(row_heights) + 58
    image = Image.new("RGB", (width, max(height, 250)), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width, header_height), radius=12, fill="#12344d")
    draw.text((margin, 25), "NONEBOT PLUGIN", font=_font(14, bold=True), fill="#b7d9d6")
    draw.text((margin, 52), str(page.title), font=_font(31, bold=True), fill="#ffffff")
    draw.text((margin, 94), str(page.subtitle), font=_font(15), fill="#d7e5ed")

    y = header_height
    draw.rectangle((margin, y, width - margin, y + table_header_height), fill="#e8eff6")
    x = margin
    for index, column in enumerate(columns):
        draw.text((x + 11, y + 12), str(column), font=header_font, fill="#486581")
        x += widths[index]
    y += table_header_height
    for row, cells, row_height in zip(rows, cell_lines, row_heights):
        draw.rectangle((margin, y, width - margin, y + row_height), fill="#ffffff")
        draw.line((margin, y + row_height, width - margin, y + row_height), fill="#d9e2ec")
        x = margin
        for index, lines in enumerate(cells):
            for line_index, line in enumerate(lines):
                draw.text((x + 11, y + 10 + line_index * 25), line, font=body_font, fill="#243b53")
            x += widths[index]
        y += row_height
    draw.text((width - margin - 120, y + 18), f"第 {page.index} / {page.total} 页", font=_font(14), fill="#829ab1")
    result = BytesIO()
    image.save(result, format="PNG", optimize=True)
    return result.getvalue()
