"""从 NoneBot 事件提取跨适配器的共享会话范围。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nonebot.adapters import Event


@dataclass(frozen=True)
class EventScope:
    """用于访问控制的稳定会话范围，而非按用户拆分的逻辑会话。"""

    identifier: str
    kind: str

    @property
    def is_private(self) -> bool:
        return self.kind == "private"

    @property
    def is_shared(self) -> bool:
        return self.kind in {"group", "channel"}


def _adapter_namespace(event: Event) -> str:
    """从事件模块推导适配器命名空间，避免不同平台原始 ID 冲突。"""
    module = type(event).__module__
    marker = "nonebot.adapters."
    if marker in module:
        suffix = module.split(marker, maxsplit=1)[1]
        parts = suffix.split(".")
        if parts:
            return ".".join(part for part in parts if part not in {"event", "message"})
    return type(event).__module__.replace(".", "_")


def _attribute(event: Event, name: str) -> str:
    value = getattr(event, name, None)
    return str(value) if value not in (None, "") else ""


def _object_attribute(value: Any, name: str) -> str:
    attribute = getattr(value, name, None)
    return str(attribute) if attribute not in (None, "") else ""


def _is_direct_kind(value: Any) -> bool:
    kind = _object_attribute(value, "type").lower()
    return "direct" in kind or "private" in kind or kind in {"dm", "friend"}


def resolve_event_scope(event: Event) -> EventScope:
    """按事件提供的通用范围属性识别私聊、群组、频道或兜底会话。"""
    adapter = _adapter_namespace(event)
    group = _attribute(event, "group_id") or _attribute(event, "group_openid")
    if group:
        return EventScope(f"{adapter}:group:{group}", "group")

    guild = _attribute(event, "guild_id")
    channel = _attribute(event, "channel_id")
    if channel:
        identifier = f"{guild}:{channel}" if guild else channel
        return EventScope(f"{adapter}:channel:{identifier}", "channel")

    chat = _attribute(event, "chat_id")
    if chat:
        chat_object = getattr(event, "chat", None)
        kind = "private" if chat_object and _is_direct_kind(chat_object) else "group"
        return EventScope(f"{adapter}:{kind}:{chat}", kind)

    channel_object = getattr(event, "channel", None)
    channel_id = _object_attribute(channel_object, "id")
    if channel_id:
        kind = "private" if _is_direct_kind(channel_object) else "channel"
        return EventScope(f"{adapter}:{kind}:{channel_id}", kind)

    session_id = event.get_session_id()
    return EventScope(f"{adapter}:private:{session_id}", "private")
