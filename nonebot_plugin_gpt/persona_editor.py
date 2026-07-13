"""人设创建向导使用的适配器无关校验规则。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


class PersonaValidationError(ValueError):
    """用户输入未满足人设创建规则。"""


def extract_text(value: Any) -> str:
    """从任意适配器消息或参数对象中读取纯文本。"""
    extract_plain_text = getattr(value, "extract_plain_text", None)
    if callable(extract_plain_text):
        return str(extract_plain_text())
    return str(value or "")


def validate_name(name: str, existing: Mapping[str, Any], banned_words: Iterable[str]) -> str:
    """校验并规范化人设名称。"""
    normalized = name.strip()
    if not normalized:
        raise PersonaValidationError("人设名称不能为空。")
    if len(normalized) > 15:
        raise PersonaValidationError("人设名称不能超过 15 个字符。")
    if normalized in existing:
        raise PersonaValidationError("该人设名称已存在，请换一个。")
    if any(word and word in normalized for word in banned_words):
        raise PersonaValidationError("人设名称包含屏蔽词。")
    return normalized


def parse_r18(value: str) -> bool:
    """解析 R18 选项。"""
    normalized = value.strip()
    if normalized == "是":
        return True
    if normalized == "否":
        return False
    raise PersonaValidationError("请输入“是”或“否”。")


def parse_visibility(value: str, user_id: str) -> str:
    """解析公开范围，私有人设记录创建者。"""
    normalized = value.strip()
    if normalized == "公开":
        return ""
    if normalized == "私有":
        return user_id
    raise PersonaValidationError("请输入“公开”或“私有”。")


def validate_value(value: str, banned_words: Iterable[str]) -> str:
    """校验人设正文。"""
    if not value.strip():
        raise PersonaValidationError("人设内容不能为空。")
    if any(word and word in value for word in banned_words):
        raise PersonaValidationError("人设内容包含屏蔽词。")
    return value
