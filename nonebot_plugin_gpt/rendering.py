"""将 ChatGPT 富内容投影为机器人消息的适配器无关决策。"""

from dataclasses import dataclass, field
import re

from ChatGPTWeb import ChatContent, ChatResult


_COMPLEX_MARKDOWN = re.compile(r"(?m)^#{1,6}\s|^\s*[-*+]\s|^\s*\||```")


@dataclass(frozen=True)
class RenderPlan:
    """可直接转换为 UniMessage 的平台无关响应投影。"""

    text: str
    markdown_image_required: bool = False
    image_urls: list[str] = field(default_factory=list)
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


def build_render_plan(result: ChatResult, supports_markdown: bool = False) -> RenderPlan:
    """让渲染策略与传输实现、适配器消息段类型保持分离。"""
    content = result.content
    return RenderPlan(
        text=text_for_platform(content, supports_markdown),
        markdown_image_required=not supports_markdown and should_render_markdown_image(content),
        image_urls=result.image_urls.copy(),
        model=result.used_model or result.requested_model,
        usage=result.usage.copy(),
    )
