"""适配器无关的访问控制与内容安全规则。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from nonebot.adapters import Event
from nonebot.log import logger
from nonebot.matcher import Matcher

from .config import config_gpt, config_nb
from .event_scope import resolve_event_scope
from .source import ban_str_path, banpath, plusstatus, whitepath


def get_event_user_id(event: Event) -> str | None:
    """安全读取事件发送者；无上下文事件不参与聊天或命令匹配。"""
    try:
        user_id = event.get_user_id()
    except (AttributeError, ValueError):
        return None
    user_id = str(user_id).strip()
    return user_id or None


def get_access_session_id(event: Event) -> str:
    """返回用于访问控制的共享会话范围标识。"""
    try:
        return resolve_event_scope(event).identifier
    except (AttributeError, ValueError):
        return ""


def get_participant_key(event: Event) -> str:
    """返回会话内唯一的参与者标识，用于局部封禁等安全策略。"""
    user_id = get_event_user_id(event)
    if not user_id:
        return ""
    session_id = get_access_session_id(event)
    return f"{session_id}::{user_id}" if session_id else ""


def _read_json(path, fallback: dict[str, object]) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback.copy()
    return value if isinstance(value, dict) else fallback.copy()


def read_whitelist() -> dict[str, object]:
    """读取 v2 白名单，并保留旧版分组数据用于兼容授权。"""
    raw = _read_json(whitepath, {})
    sessions = raw.get("sessions", [])
    legacy = raw.get("legacy", {})
    if not isinstance(legacy, dict):
        legacy = {}
    legacy = {
        **legacy,
        "group": raw.get("group", legacy.get("group", [])),
        "private": raw.get("private", legacy.get("private", [])),
        "qqgroup": raw.get("qqgroup", legacy.get("qqgroup", [])),
        "qqguild": raw.get("qqguild", legacy.get("qqguild", [])),
        "session": raw.get("session", legacy.get("session", [])),
    }
    return {
        "version": 2,
        "sessions": [str(value) for value in sessions if isinstance(value, str)],
        "legacy": {
            name: [str(value) for value in values if isinstance(value, (str, int))]
            for name, values in legacy.items()
            if isinstance(values, list)
        },
    }


def write_whitelist(value: dict[str, object]) -> None:
    whitepath.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _legacy_whitelist_matches(event: Event, whitelist: dict[str, object]) -> bool:
    legacy = whitelist.get("legacy", {})
    if not isinstance(legacy, dict):
        return False
    raw_values = {
        str(getattr(event, name, ""))
        for name in ("group_id", "group_openid", "guild_id", "channel_id")
    }
    raw_values.discard("")
    user_id = get_event_user_id(event)
    session_id = str(event.get_session_id())
    group_values = {str(value) for value in legacy.get("group", [])}
    qq_group_values = {str(value) for value in legacy.get("qqgroup", [])}
    private_values = {str(value) for value in legacy.get("private", [])}
    guild_values = {str(value) for value in legacy.get("qqguild", [])}
    session_values = {str(value) for value in legacy.get("session", [])}
    return bool(
        raw_values & (group_values | qq_group_values | guild_values)
        or (_is_private_session(event) and user_id and user_id in private_values)
        or session_id in session_values
        or get_access_session_id(event) in session_values
    )


def is_whitelisted(event: Event) -> bool:
    """判断当前范围是否处于新版或旧版白名单。"""
    whitelist = read_whitelist()
    return (
        get_access_session_id(event) in whitelist["sessions"]
        or _legacy_whitelist_matches(event, whitelist)
    )


def is_banned(event: Event, bans: dict[str, object] | None = None) -> bool:
    """兼容旧版按用户 ID 封禁与新版按会话参与者封禁。"""
    records = bans if bans is not None else _read_json(banpath, {})
    user_id = get_event_user_id(event)
    return bool(get_participant_key(event) in records or (user_id and user_id in records))


def _event_plain_text(event: Event) -> str:
    """读取适配器通用的纯文本消息，缺失时安全降级为空字符串。"""
    get_plaintext = getattr(event, "get_plaintext", None)
    if callable(get_plaintext):
        return str(get_plaintext())
    get_message = getattr(event, "get_message", None)
    if callable(get_message):
        message = get_message()
        extract_plain_text = getattr(message, "extract_plain_text", None)
        if callable(extract_plain_text):
            return str(extract_plain_text())
    return ""


def _message_plain_text(message: Any) -> str:
    """读取跨适配器消息对象的纯文本。"""
    extract_plain_text = getattr(message, "extract_plain_text", None)
    if callable(extract_plain_text):
        return str(extract_plain_text())
    return str(message or "")


def _addressed_to_bot(event: Event) -> bool:
    """适配器未提供 to_me 时按未提及处理。"""
    return bool(getattr(event, "to_me", False))


def _is_private_session(event: Event) -> bool:
    """识别适配器的私聊范围。"""
    try:
        return resolve_event_scope(event).is_private
    except (AttributeError, ValueError):
        return False


async def plus_status(event: Event) -> bool:
    """判断事件是否允许使用付费模型命令。"""
    user_id = get_event_user_id(event)
    if not user_id:
        return False
    if user_id in config_nb.superusers:
        return True
    bans = _read_json(banpath, {})
    if is_banned(event, bans):
        return False
    if not config_gpt.gpt_plus_white_list_mode:
        return True
    configured = _read_json(plusstatus, {"status": True})
    return bool(
        configured.get("status", True)
        and get_access_session_id(event) in configured
    )


async def gpt_rule(event: Event) -> bool:
    """聊天事件匹配规则。"""
    if not get_event_user_id(event):
        return False
    is_prefixed = any(
        _event_plain_text(event).startswith(prefix)
        for prefix in config_gpt.gpt_chat_start
    )
    if not (_addressed_to_bot(event) or _is_private_session(event) or is_prefixed):
        return False
    bans = _read_json(banpath, {})
    if is_banned(event, bans):
        return False
    if not config_gpt.gpt_white_list_mode:
        return True
    return is_whitelisted(event)


async def gpt_command_rule(event: Event) -> bool:
    """已由 Alconna 精确识别的聊天命令授权规则。

    命令匹配本身已经完成，因此不能再依赖不同适配器对 ``to_me`` 的实现差异。
    """
    if not get_event_user_id(event):
        return False
    bans = _read_json(banpath, {})
    if is_banned(event, bans):
        return False
    if not config_gpt.gpt_white_list_mode:
        return True
    return is_whitelisted(event)


async def gpt_manage_rule(event: Event) -> bool:
    """管理事件匹配。"""
    user_id = get_event_user_id(event)
    if not user_id:
        return False
    return (
        user_id in config_nb.superusers
        or get_access_session_id(event) in config_gpt.gpt_manage_ids
    )


async def gpt_persona_editor_rule(event: Event) -> bool:
    """允许已授权用户创建人设，也让管理员可在任意会话维护人设。"""
    return await gpt_manage_rule(event) or await gpt_command_rule(event)


async def gpt_operator_command_rule(event: Event) -> bool:
    """管理者可在未加白会话使用维护命令，普通用户仍需白名单授权。"""
    return await gpt_manage_rule(event) or await gpt_command_rule(event)


async def gpt_superuser_rule(event: Event) -> bool:
    """仅允许 NoneBot 超级用户执行高风险的本地运维入口。"""
    user_id = get_event_user_id(event)
    return bool(user_id and user_id in config_nb.superusers)


async def gpt_cdk_redeem_rule(event: Event) -> bool:
    """允许未入白名单的正常用户兑换 CDK。"""
    if not get_event_user_id(event):
        return False
    bans = _read_json(banpath, {})
    return not is_banned(event, bans)


async def add_white(session_id: str, plus: bool = False) -> str:
    """添加一个精确会话标识到白名单。"""
    whitelist = read_whitelist()
    sessions = whitelist["sessions"]
    if session_id in sessions:
        return "白名单已存在"
    if plus:
        configured = _read_json(plusstatus, {"status": True})
        configured[session_id] = "auto"
        plusstatus.write_text(
            json.dumps(configured, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    sessions.append(session_id)
    write_whitelist(whitelist)
    return "添加成功"


async def del_white(session_id: str) -> str:
    """删除一个精确会话标识及其 Plus 授权。"""
    whitelist = read_whitelist()
    sessions = whitelist["sessions"]
    if session_id not in sessions:
        return "不在白名单中"
    configured = _read_json(plusstatus, {"status": True})
    configured.pop(session_id, None)
    plusstatus.write_text(
        json.dumps(configured, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sessions.remove(session_id)
    write_whitelist(whitelist)
    return "删除成功"


async def add_ban(participant_key: str, value: str) -> None:
    """封禁会话内参与者。"""
    bans = _read_json(banpath, {})
    entries = bans.setdefault(participant_key, [])
    if isinstance(entries, list):
        entries.append(value)
    banpath.write_text(
        json.dumps(bans, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def ban_check(event: Event, matcher: Matcher, text: Any = None) -> None:
    """执行参与者封禁和关键词封禁检查。"""
    participant_key = get_participant_key(event)
    bans = _read_json(banpath, {})
    if is_banned(event, bans):
        await matcher.finish()
    plain_text = _message_plain_text(text)
    if not plain_text:
        return
    for banned_word in ban_str_path.read_text(encoding="utf-8").splitlines():
        if banned_word and banned_word in plain_text:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            detail = (
                f"{current_time} 在 {get_access_session_id(event)} 中触发屏蔽词 "
                f"{banned_word}\n{plain_text}"
            )
            logger.info(
                "屏蔽词黑名单触发，屏蔽词：%s\n触发人：%s\n原语句：%s",
                banned_word,
                event.get_user_id(),
                detail,
            )
            await add_ban(participant_key, detail)
            await matcher.finish()
