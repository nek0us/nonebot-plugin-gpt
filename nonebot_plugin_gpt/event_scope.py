"""从 NoneBot 事件提取跨适配器的共享会话范围。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from nonebot.adapters import Event


GROUP_SPEAKER_TAG = "[群聊发言者]"
RECENT_GROUP_CONTEXT_TAG = "[最近群聊上下文]"
RECENT_GROUP_CONTEXT_END_TAG = "[最近群聊上下文结束]"
CURRENT_SPEAKER_RULE = "本轮只回复此发言者；不得沿用共享会话历史中的其他姓名"


def strip_recent_group_context_prompt(message: str) -> str:
    """Remove ambient group context before projecting stored user messages."""
    value = str(message or "")
    if not value.startswith(RECENT_GROUP_CONTEXT_TAG):
        return value
    _context, separator, remainder = value.partition(RECENT_GROUP_CONTEXT_END_TAG)
    return remainder.lstrip("\r\n") if separator else value


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


def get_adapter_namespace(event: Event) -> str:
    """返回稳定的适配器命名空间，供跨会话个人授权使用。"""
    return _adapter_namespace(event)


def _attribute(event: Event, name: str) -> str:
    value = getattr(event, name, None)
    return str(value) if value not in (None, "") else ""


def _object_attribute(value: Any, name: str) -> str:
    if isinstance(value, Mapping):
        attribute = value.get(name)
        return str(attribute) if attribute not in (None, "") else ""
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


def resolve_participant_identity(event: Event) -> str:
    """返回平台内稳定的用户标识，不携带群聊或私聊范围。"""
    user_id = str(event.get_user_id()).strip()
    if not user_id:
        raise ValueError("event does not contain a user id")
    adapter = _adapter_namespace(event)
    login = getattr(event, "login", None)
    platform = _object_attribute(login, "platform") or _attribute(event, "platform")
    namespace = f"{adapter}:{platform}" if platform else adapter
    return f"{namespace}:user:{user_id}"


def resolve_participant_display_name(event: Event) -> str:
    """尽量读取各适配器提供的昵称，仅用于帮助模型自然称呼发言者。"""
    candidates = (
        getattr(event, "sender", None),
        getattr(event, "member", None),
        getattr(event, "user", None),
        getattr(event, "author", None),
        getattr(event, "from_user", None),
    )
    for candidate in candidates:
        for attribute in ("card", "nick", "nickname", "name", "username"):
            value = " ".join(_object_attribute(candidate, attribute).split())
            if value:
                return value[:80]
    return ""


def format_group_speaker_prompt(event: Event, message: str) -> str:
    """以固定短标签将群聊发言者资料附加到当前模型输入。"""
    identity = resolve_participant_identity(event)
    metadata = {
        "id": identity,
        "name": resolve_participant_display_name(event) or None,
        # 这是本轮实际发言者，不应被共享群聊历史中的旧称呼覆盖。
        "current": True,
        "reply_target": True,
        "rule": CURRENT_SPEAKER_RULE,
    }
    return f"{GROUP_SPEAKER_TAG} {json.dumps(metadata, ensure_ascii=False)}\n{message}"


def project_group_speaker_prompt(message: str, *, anonymize: bool = False) -> tuple[str, str]:
    """将内部群聊发言者标签投影为历史视图可用的身份与正文。"""
    message = strip_recent_group_context_prompt(message)
    if message.startswith(GROUP_SPEAKER_TAG):
        header, separator, body = message.partition("\n")
        try:
            metadata = json.loads(header.removeprefix(GROUP_SPEAKER_TAG).strip())
        except json.JSONDecodeError:
            metadata = None
        if isinstance(metadata, dict) and separator:
            if anonymize:
                return "用户", body.strip()
            name = " ".join(str(metadata.get("name") or "").split())
            identity = str(metadata.get("id") or "").strip()
            if name:
                return f"用户 · {name[:80]}", body.strip()
            if identity:
                return f"用户 · {identity.rsplit(':', maxsplit=1)[-1]}", body.strip()
            return "用户", body.strip()
    return "用户", strip_group_speaker_prompt(message)


def group_speaker_identity(message: str) -> str:
    """提取历史投影可选展示的稳定发言者 ID，不把内部标签原样暴露给用户。"""
    message = strip_recent_group_context_prompt(message)
    if not message.startswith(GROUP_SPEAKER_TAG):
        return ""
    header, separator, _ = message.partition("\n")
    if not separator:
        return ""
    try:
        metadata = json.loads(header.removeprefix(GROUP_SPEAKER_TAG).strip())
    except json.JSONDecodeError:
        return ""
    return str(metadata.get("id") or "").strip() if isinstance(metadata, dict) else ""


def extract_group_speaker_tag(message: str) -> str:
    """从普通输入或内部事件中提取一行合法的群聊发言者标签。"""
    for line in str(message or "").splitlines():
        if not line.startswith(GROUP_SPEAKER_TAG):
            continue
        try:
            metadata = json.loads(line.removeprefix(GROUP_SPEAKER_TAG).strip())
        except json.JSONDecodeError:
            continue
        if isinstance(metadata, dict):
            return line.strip()
    return ""


def strip_group_speaker_prompt(message: str) -> str:
    """从上游历史记录中移除插件写入的群聊发言者标签。"""
    message = strip_recent_group_context_prompt(message)
    if message.startswith(GROUP_SPEAKER_TAG):
        header, separator, body = message.partition("\n")
        metadata = header.removeprefix(GROUP_SPEAKER_TAG).strip()
        try:
            value = json.loads(metadata)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict) and separator:
            return body.strip()

    legacy_prefix = "发言者资料："
    legacy_message_prefix = "用户消息："
    if message.startswith("这是多人会话中的一条用户消息。"):
        _, separator, body = message.partition(legacy_prefix)
        if separator:
            _, separator, body = body.partition("\n")
            if separator and body.startswith(legacy_message_prefix):
                return body.removeprefix(legacy_message_prefix).strip()
    return message
