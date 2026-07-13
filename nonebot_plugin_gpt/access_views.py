"""跨平台访问控制命令的参数解析和文本投影。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def parse_access_target(value: str, *, default_target: str = "") -> tuple[str, bool]:
    """解析“[plus] [会话标识]”格式的管理参数。"""
    parts = value.strip().split()
    paid = bool(parts and parts[0].lower() == "plus")
    if paid:
        parts.pop(0)
    if len(parts) > 1:
        raise ValueError("参数过多，请使用“[plus] [会话标识]”。")
    target = parts[0] if parts else default_target
    if not target:
        raise ValueError("请提供会话标识，或在目标会话中执行该命令。")
    return target, paid


def format_bans(bans: Mapping[str, Any], target: str = "") -> str:
    """生成简洁的黑名单文本。"""
    keys = [target] if target else list(bans)
    lines = ["黑名单"]
    for key in keys:
        values = bans.get(key)
        if not isinstance(values, list) or not values:
            continue
        lines.append(f"{key}：{str(values[0]).replace(chr(10), ' ')[:180]}")
    return "\n".join(lines) if len(lines) > 1 else "黑名单为空。"


def format_whitelist(whitelist: Mapping[str, Any], paid: Mapping[str, Any]) -> str:
    """生成白名单与 Plus 标记的跨平台文本。"""
    lines = ["白名单"]
    for identifier in whitelist.get("sessions", []):
        marker = "，Plus" if str(identifier) in paid else ""
        lines.append(f"会话：{identifier}{marker}")
    return "\n".join(lines) if len(lines) > 1 else "白名单为空。"
