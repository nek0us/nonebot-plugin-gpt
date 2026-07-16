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


def _direct_address_prompt(
    body: str,
    *,
    context_prompt: str,
    empty_trigger_prompt: str,
) -> str:
    header = context_prompt.strip()
    if not body:
        return f"{header}\n{empty_trigger_prompt}"
    return f"{header}\n用户消息：{body}"


def build_chat_prompt(
    raw_text: str,
    *,
    original_text: str = "",
    nicknames: list[str] | None = None,
    chat_prefixes: list[str],
    include_prefix: bool,
    empty_trigger_prompt: str,
    direct_address_context_enabled: bool = False,
    direct_address_context_prompt: str = "",
) -> str:
    """整理称呼触发的原始文本；默认保留自然主语，不注入额外解释。"""
    text = raw_text.strip()
    original = original_text.strip() or text
    nickname = _match_prefix(original, nicknames or [])
    if nickname:
        if _only_repeated_prefix(original, nickname):
            if not direct_address_context_enabled:
                return empty_trigger_prompt
            return _direct_address_prompt(
                "",
                context_prompt=direct_address_context_prompt,
                empty_trigger_prompt=empty_trigger_prompt,
            )
        if not direct_address_context_enabled:
            return original
        return _direct_address_prompt(
            original,
            context_prompt=direct_address_context_prompt,
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
    if not direct_address_context_enabled:
        return body or empty_trigger_prompt
    return _direct_address_prompt(
        body,
        context_prompt=direct_address_context_prompt,
        empty_trigger_prompt=empty_trigger_prompt,
    )
