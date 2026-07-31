"""将聊天触发文本整理为适合交给模型的对话语境。"""

from __future__ import annotations

from typing import Any, Sequence

from nonebot_plugin_alconna.uniseg import (
    At,
    AtAll,
    Audio,
    Emoji,
    File,
    Image,
    Text,
    UniMessage,
    Video,
    Voice,
)


def _segment_text(
    segment: Any,
    *,
    image_upload_enabled: bool,
    file_upload_enabled: bool,
) -> str:
    if isinstance(segment, Text):
        return segment.text
    if isinstance(segment, At):
        display = " ".join((segment.display or "").split())
        target = str(segment.target).strip()
        label = display or target or "未知对象"
        kind = {
            "user": "用户",
            "role": "身份组",
            "channel": "频道",
        }.get(segment.flag, "对象")
        identifier = f"{kind}ID：{target}" if target else ""
        return f"@{label}（{identifier}）" if identifier else f"@{label}"
    if isinstance(segment, AtAll):
        return "@全体成员"
    if isinstance(segment, Image):
        state = "已附加" if image_upload_enabled else "未上传，无法读取"
        return f"【图片附件：{segment.name or '未命名图片'}，{state}】"
    if isinstance(segment, (Audio, Voice)):
        state = "已附加" if file_upload_enabled else "未上传，无法读取"
        return f"【音频附件：{segment.name or '未命名音频'}，{state}】"
    if isinstance(segment, Video):
        state = "已附加" if file_upload_enabled else "未上传，无法读取"
        return f"【视频附件：{segment.name or '未命名视频'}，{state}】"
    if isinstance(segment, File):
        state = "已附加" if file_upload_enabled else "未上传，无法读取"
        return f"【文件附件：{segment.name or '未命名文件'}，{state}】"
    if isinstance(segment, Emoji):
        return f"【表情：{segment.name or segment.id}】"
    return ""


def extract_chat_message(
    message: Any,
    *,
    self_id: str = "",
    image_upload_enabled: bool = False,
    file_upload_enabled: bool = False,
    uploaded_files: Sequence[Any] | None = None,
) -> str:
    """保留跨平台消息中的文本与提及语义，移除仅用于唤醒机器人的 @。"""
    if isinstance(message, UniMessage):
        segments = message
    else:
        try:
            segments = UniMessage.of(message)
        except Exception:
            extract_plain_text = getattr(message, "extract_plain_text", None)
            return str(extract_plain_text() if callable(extract_plain_text) else message or "")

    bot_id = str(self_id).strip()
    uploaded_images = None
    uploaded_others = None
    if uploaded_files is not None:
        uploaded_images = sum(
            1
            for item in uploaded_files
            if (
                getattr(item, "content_type", None) == "image_asset_pointer"
                or str(getattr(item, "mime_type", "") or "").lower().startswith("image/")
            )
        )
        uploaded_others = len(uploaded_files) - uploaded_images
    parts: list[str] = []
    for segment in segments:
        if isinstance(segment, At) and segment.flag == "user" and bot_id and segment.target == bot_id:
            continue
        segment_image_enabled = image_upload_enabled
        segment_file_enabled = file_upload_enabled
        if isinstance(segment, Image) and uploaded_images is not None:
            segment_image_enabled = uploaded_images > 0
            uploaded_images = max(0, uploaded_images - 1)
        elif isinstance(segment, (Audio, Voice, Video, File)) and uploaded_others is not None:
            segment_file_enabled = uploaded_others > 0
            uploaded_others = max(0, uploaded_others - 1)
        parts.append(
            _segment_text(
                segment,
                image_upload_enabled=segment_image_enabled,
                file_upload_enabled=segment_file_enabled,
            )
        )
    return "".join(parts)


def attachment_segment_counts(message: Any) -> tuple[int, int]:
    """Return image and non-image attachment counts from one unified message."""
    if isinstance(message, UniMessage):
        segments = message
    else:
        try:
            segments = UniMessage.of(message)
        except Exception:
            return 0, 0
    images = sum(isinstance(segment, Image) for segment in segments)
    files = sum(
        isinstance(segment, (Audio, Voice, Video, File))
        for segment in segments
    )
    return images, files


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
