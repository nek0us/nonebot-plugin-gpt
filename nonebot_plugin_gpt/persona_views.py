"""人设数据的跨平台文本投影。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nonebot_plugin_alconna.uniseg import UniMessage


def list_personas(personality: Any, metadata: Mapping[str, Any]) -> UniMessage:
    """生成适合所有适配器发送的人设摘要列表。"""
    personas = getattr(personality, "init_list", [])
    if not personas:
        return UniMessage.text("还没有可用人设。")
    lines = ["人设列表"]
    indexed_personas = enumerate(personas, start=1)
    for index, item in reversed(list(indexed_personas)):
        name = str(item.get("name", "")) if isinstance(item, Mapping) else ""
        details = metadata.get(name, {})
        r18 = "R18" if isinstance(details, Mapping) and details.get("r18") else "普通"
        visibility = "私有" if isinstance(details, Mapping) and details.get("open") else "公开"
        lines.append(f"{index}. {name or '未命名'} ({r18}, {visibility})")
    return UniMessage.text("\n".join(lines))


def show_persona(personality: Any, metadata: Mapping[str, Any], name: str, user_id: str) -> UniMessage:
    """读取一份人设，并在这里统一执行私有人设可见性判断。"""
    if not name:
        return UniMessage.text("请输入要查看的人设名称。")
    details = metadata.get(name)
    if not isinstance(details, Mapping):
        return UniMessage.text("没有找到指定人设，请检查名称。")
    owner = str(details.get("open", ""))
    if owner and owner != user_id:
        return UniMessage.text("其他用户的私有人设不能查看。")
    value = getattr(personality, "get_value_by_name", lambda _name: "")(name)
    if not value:
        return UniMessage.text("没有找到指定人设，请检查名称。")
    return UniMessage.text(str(value))
