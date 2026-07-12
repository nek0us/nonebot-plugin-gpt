"""Adapter-neutral decisions for projecting ChatGPT rich content into bot messages."""

import re

from ChatGPTWeb import ChatContent


_COMPLEX_MARKDOWN = re.compile(r"(?m)^#{1,6}\s|^\s*[-*+]\s|^\s*\||```")


def text_for_platform(content: ChatContent, supports_markdown: bool) -> str:
    """Keep Markdown only where the outbound platform can present it faithfully."""
    if supports_markdown:
        return content.markdown
    return content.plain_text or content.markdown


def should_render_markdown_image(content: ChatContent) -> bool:
    """Reserve image rendering for formatting that plain bot text would lose."""
    return bool(
        content.code_blocks
        or content.rich_items
        or _COMPLEX_MARKDOWN.search(content.markdown)
    )
