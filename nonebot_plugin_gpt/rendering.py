"""将 ChatGPT 富内容投影为机器人消息的适配器无关决策。"""

from dataclasses import dataclass, field
import re
from typing import Literal
from urllib.parse import urlparse

from ChatGPTWeb import ChatContent, ChatResult
from ChatGPTWeb.config import IOFile


_COMPLEX_MARKDOWN = re.compile(r"(?m)^#{1,6}\s|^\s*[-*+]\s|^\s*\||```")
_MARKDOWN_LINK = re.compile(r"(?<!!)\[(?P<label>[^\]]+)\]\((?P<url>[^\s)]+)(?:\s+['\"][^)]*['\"])?\)")


def _is_private_chatgpt_asset_url(value: str) -> bool:
    """Adapters cannot download ChatGPT's cookie-protected asset endpoints."""
    parsed = urlparse(value)
    return (
        parsed.hostname in {"chatgpt.com", "chat.openai.com"}
        and parsed.path.startswith("/backend-api/")
    )


@dataclass(frozen=True)
class RenderPlan:
    """可直接转换为 UniMessage 的平台无关响应投影。"""

    text: str
    markdown: str = ""
    markdown_image_required: bool = False
    native_markdown: bool = False
    reference_text: str = ""
    image_urls: list[str] = field(default_factory=list)
    files: list[IOFile] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)


def text_for_platform(content: ChatContent, supports_markdown: bool) -> str:
    """仅在输出平台能够正确呈现时保留 Markdown。"""
    if supports_markdown:
        return content.markdown
    return content.plain_text or content.markdown


def should_render_markdown_image(content: ChatContent) -> bool:
    """仅将纯文本会明显丢失格式的信息交给图片渲染。"""
    return bool(
        content.code_blocks
        or content.rich_items
        or _COMPLEX_MARKDOWN.search(content.markdown)
    )


def _number_image_links(markdown: str) -> tuple[str, str]:
    """把图片中不可点击的 Markdown 链接投影为编号与参考清单。"""
    indexes: dict[tuple[str, str], int] = {}
    references: list[tuple[int, str, str]] = []

    def replace(match: re.Match[str]) -> str:
        label = match.group("label").strip()
        url = match.group("url").strip()
        key = (label, url)
        index = indexes.get(key)
        if index is None:
            index = len(references) + 1
            indexes[key] = index
            references.append((index, label, url))
        return f"{label}[{index}]"

    projected = _MARKDOWN_LINK.sub(replace, markdown)
    if not references:
        return projected, ""
    image_references = "\n".join(
        f"[{index}] {label} · {urlparse(url).netloc or url}"
        for index, label, url in references
    )
    reference_text = "参考链接\n" + "\n".join(
        f"[{index}] {label}\n{url}"
        for index, label, url in references
    )
    return f"{projected}\n\n---\n\n### 参考链接\n\n{image_references}", reference_text


def build_render_plan(
    result: ChatResult,
    supports_markdown: bool = False,
    render_mode: Literal["auto", "text", "image"] = "auto",
) -> RenderPlan:
    """让渲染策略与传输实现、适配器消息段类型保持分离。"""
    content = result.content
    markdown = content.markdown or result.text
    text = text_for_platform(content, supports_markdown) or result.text
    if render_mode == "image":
        markdown_image_required = bool(markdown) and not supports_markdown
    elif render_mode == "text":
        markdown_image_required = False
    else:
        markdown_image_required = not supports_markdown and should_render_markdown_image(content)
    image_markdown = markdown
    reference_text = ""
    if markdown_image_required:
        image_markdown, reference_text = _number_image_links(markdown)
    return RenderPlan(
        text=text,
        markdown=image_markdown,
        markdown_image_required=markdown_image_required,
        native_markdown=bool(supports_markdown and markdown),
        reference_text=reference_text,
        image_urls=[
            url
            for url in (result.image_urls or content.image_urls)
            if not _is_private_chatgpt_asset_url(url)
        ],
        files=list(getattr(result, "files", [])),
        model=result.used_model or result.requested_model,
        usage=result.usage.copy(),
    )
