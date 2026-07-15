"""将聊天触发文本整理为适合交给模型的对话语境。"""

from __future__ import annotations


def _only_repeated_prefix(text: str, prefix: str) -> bool:
    compact_text = "".join(text.split())
    compact_prefix = "".join(prefix.split())
    return bool(compact_prefix and compact_text and not compact_text.replace(compact_prefix, ""))


def _match_prefix(text: str, prefixes: list[str]) -> str:
    folded_text = text.casefold()
    for prefix in prefixes:
        normalized = prefix.strip()
        if normalized and folded_text.startswith(normalized.casefold()):
            return normalized
    return ""


def _direct_address_prompt(body: str, *, addressed_as: str, empty_trigger_prompt: str) -> str:
    header = "【对话语境】用户正在直接称呼你。"
    if addressed_as:
        header += (
            f"用户使用的称呼：{addressed_as}。该称呼可能只是机器人路由别名，"
            "不要把它强行当成当前角色名称。"
        )
    if not body:
        return f"{header}\n{empty_trigger_prompt}"
    return f"{header}\n请结合当前人设理解消息中被省略的主语。\n用户消息：{body}"


def build_chat_prompt(
    raw_text: str,
    *,
    original_text: str = "",
    nicknames: list[str] | None = None,
    chat_prefixes: list[str],
    include_prefix: bool,
    empty_trigger_prompt: str,
) -> str:
    """保留“正在直接称呼机器人”的语境，同时避免把路由别名当成人设名称。"""
    text = raw_text.strip()
    original = original_text.strip() or text
    nickname = _match_prefix(original, nicknames or [])
    if nickname:
        body = text
        if _match_prefix(body, [nickname]):
            body = body[len(nickname):].strip()
        if _only_repeated_prefix(original, nickname):
            body = ""
        return _direct_address_prompt(
            body,
            addressed_as=nickname,
            empty_trigger_prompt=empty_trigger_prompt,
        )

    if include_prefix:
        return text or empty_trigger_prompt

    matched_prefix = _match_prefix(text, chat_prefixes)
    if not matched_prefix:
        return text or empty_trigger_prompt

    body = text[len(matched_prefix):].strip()
    if not body or _only_repeated_prefix(text, matched_prefix):
        body = ""
    return _direct_address_prompt(
        body,
        addressed_as="",
        empty_trigger_prompt=empty_trigger_prompt,
    )
