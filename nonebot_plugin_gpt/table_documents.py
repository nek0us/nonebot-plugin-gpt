"""面向列表命令的跨平台表格图片文档。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Any

from .image_fallback import render_table_page, use_local_font_renderer


_STYLE = """
* { box-sizing: border-box; }
body { margin: 0; color: #29384f; background: #f6f7fb; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
.sheet { width: 960px; padding: 30px; background: #f6f7fb; }
.header { padding: 24px 28px; border: 1px solid #e3e6f0; border-left: 7px solid #75a8d9; border-radius: 10px 10px 0 0; background: #ffffff; }
h1 { margin: 0; color: #2c3654; font-size: 30px; line-height: 1.25; }
.subtitle { margin: 8px 0 0; color: #737b91; font-size: 14px; line-height: 1.55; }
.table-wrap { overflow: hidden; border: 1px solid #e3e6f0; border-top: 0; border-radius: 0 0 10px 10px; background: #ffffff; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th { padding: 12px 14px; color: #6149ad; background: #eee9ff; border-bottom: 1px solid #ddd5fb; font-size: 13px; text-align: left; }
td { padding: 13px 14px; color: #29384f; border-bottom: 1px solid #edf0f5; font-size: 14px; line-height: 1.55; vertical-align: top; overflow-wrap: anywhere; white-space: pre-wrap; }
tbody tr:nth-child(even) td { background: #fafbfe; }
tr:last-child td { border-bottom: 0; }
.empty { padding: 32px; color: #737b91; text-align: center; }
.footer { margin: 14px 4px 0; color: #8991a4; font-size: 12px; text-align: right; }
"""


def _as_text(value: Any) -> str:
    return str(value if value is not None else "-").strip() or "-"


@dataclass(frozen=True)
class TablePage:
    title: str
    subtitle: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    index: int
    total: int
    html: str


def build_table_pages(
    title: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    subtitle: str = "",
    rows_per_page: int = 18,
) -> tuple[TablePage, ...]:
    """将结构化行分页为可换行、可阅读的 HTML 表格。"""
    normalized_rows = [tuple(_as_text(value) for value in row) for row in rows]
    pages = [normalized_rows[index : index + rows_per_page] for index in range(0, len(normalized_rows), rows_per_page)]
    if not pages:
        pages = [[]]
    total = len(pages)
    header_cells = "".join(f"<th>{escape(_as_text(column))}</th>" for column in columns)
    result: list[TablePage] = []
    for index, page_rows in enumerate(pages, start=1):
        if page_rows:
            body = "".join(
                "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
                for row in page_rows
            )
            table = f"<table><thead><tr>{header_cells}</tr></thead><tbody>{body}</tbody></table>"
        else:
            table = '<div class="empty">暂无可展示内容。</div>'
        page_subtitle = subtitle or "结构化管理信息"
        html = (
            "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<style>{_STYLE}</style></head><body><main class=\"sheet\">"
            f"<header class=\"header\"><h1>{escape(title)}</h1>"
            f"<p class=\"subtitle\">{escape(page_subtitle)}</p></header>"
            f"<section class=\"table-wrap\">{table}</section>"
            f"<footer class=\"footer\">第 {index} / {total} 页</footer></main></body></html>"
        )
        result.append(TablePage(
            title=title,
            subtitle=page_subtitle,
            columns=tuple(_as_text(column) for column in columns),
            rows=tuple(page_rows),
            index=index,
            total=total,
            html=html,
        ))
    return tuple(result)


def persona_table_pages(personality: Any, metadata: Mapping[str, Any]) -> tuple[str, ...]:
    rows = []
    for index, item in enumerate(getattr(personality, "init_list", []), start=1):
        if not isinstance(item, Mapping):
            continue
        name = _as_text(item.get("name"))
        details = metadata.get(name, {})
        is_mapping = isinstance(details, Mapping)
        rows.append((index, name, "R18" if is_mapping and details.get("r18") else "普通", "私有" if is_mapping and details.get("open") else "公开"))
    return build_table_pages("人设列表", ("序号", "名称", "分级", "可见性"), rows, subtitle="可初始化与可查看的人设")


def blacklist_table_pages(bans: Mapping[str, Any], target: str = "") -> tuple[str, ...]:
    rows = []
    for key in ([target] if target else bans):
        values = bans.get(key)
        if isinstance(values, list) and values:
            rows.append((key, str(values[0]).replace("\n", " ")))
    return build_table_pages("黑名单列表", ("目标", "原因"), rows, subtitle="仅显示当前规则中的有效记录")


def whitelist_table_pages(whitelist: Mapping[str, Any], paid: Mapping[str, Any]) -> tuple[str, ...]:
    rows = []
    for identifier in whitelist.get("sessions", []):
        rows.append(("会话", identifier, "Plus" if str(identifier) in paid else "普通"))
    for identity in whitelist.get("users", []):
        rows.append(("个人", identity, "-"))
    legacy = whitelist.get("legacy", {})
    if isinstance(legacy, Mapping):
        for kind, values in legacy.items():
            if isinstance(values, list):
                for identifier in values:
                    rows.append((f"旧版 {kind}", identifier, "Plus" if str(identifier) in paid else "普通"))
    return build_table_pages("白名单列表", ("类型", "标识", "权限"), rows, subtitle="会话与个人授权范围")


def cdk_table_pages(records: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    rows = []
    for record in records:
        kind = "个人" if str(record.get("grant_kind") or "scope") == "participant" else "会话"
        rows.append((
            record.get("code"),
            record.get("status"),
            kind,
            record.get("note") or "-",
            record.get("created_at") or "-",
        ))
    return build_table_pages("CDK 列表", ("CDK", "状态", "授权", "来源", "创建时间"), rows, subtitle="一次性授权码及其当前状态", rows_per_page=14)


def session_table_pages(sessions: Iterable[Any], active_logical_id: str) -> tuple[str, ...]:
    rows = []
    for index, state in enumerate(sessions, start=1):
        rows.append((
            index,
            "当前" if getattr(state, "logical_id", "") == active_logical_id else "可切换",
            getattr(state, "label", "") or getattr(state, "persona_name", "") or "未命名会话",
            getattr(state, "persona_name", "") or "无",
            getattr(state, "model", "") or "auto",
            len(getattr(state, "checkpoints", [])),
        ))
    return build_table_pages("逻辑会话", ("序号", "状态", "名称", "人设", "模型", "检查点"), rows, subtitle="按最近使用排序；用“切换会话 序号”切换")


async def render_table_pages(pages: Iterable[TablePage]) -> tuple[bytes, ...]:
    """延迟渲染表格，避免 htmlkit 缺失时影响插件启动。"""
    page_list = tuple(pages)
    if use_local_font_renderer():
        return tuple(render_table_page(page) for page in page_list)

    from nonebot_plugin_htmlkit import html_to_pic

    images = []
    for page in page_list:
        images.append(await html_to_pic(page.html, dpi=120, max_width=920, device_height=10, default_font_size=15))
    return tuple(images)
