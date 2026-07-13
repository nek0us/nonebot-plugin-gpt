"""将渲染计划转换为 Alconna 跨平台 UniMessage。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from nonebot_plugin_alconna.uniseg import UniMessage

from .rendering import RenderPlan


MarkdownRenderer = Callable[[str], Awaitable[bytes | None]]


async def build_unimessage(plan: RenderPlan, render_markdown: MarkdownRenderer | None = None) -> UniMessage:
    """构造一条可跨平台发送且可优雅降级 Markdown 图片的消息。"""
    message = UniMessage()
    markdown_image = None
    if plan.markdown_image_required and render_markdown:
        markdown_image = await render_markdown(plan.text)
    if markdown_image:
        message += UniMessage.image(raw=markdown_image)
    elif plan.text:
        message += UniMessage.text(plan.text)
    for image_url in plan.image_urls:
        message += UniMessage.image(url=image_url)
    return message
