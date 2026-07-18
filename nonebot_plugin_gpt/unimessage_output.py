"""将渲染计划转换为 Alconna 跨平台 UniMessage。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import UniMessage

from .native_markdown import markdown_to_unimessage
from .rendering import RenderPlan


MarkdownRenderer = Callable[[str], Awaitable[bytes | None]]


async def build_unimessage(plan: RenderPlan, render_markdown: MarkdownRenderer | None = None) -> UniMessage:
    """构造一条可跨平台发送且可优雅降级 Markdown 图片的消息。"""
    message = UniMessage()
    markdown_image = None
    if plan.markdown_image_required and render_markdown:
        try:
            markdown_image = await render_markdown(plan.markdown or plan.text)
        except Exception as error:
            # 用户模板可能暂时不可读；此处回退纯文本，不能让正常聊天因此失败。
            logger.warning(f"聊天 Markdown 图片渲染失败，已回退文本输出：{error}")
    if markdown_image:
        message += UniMessage.image(raw=markdown_image)
        if plan.reference_text:
            message += UniMessage.text(f"\n{plan.reference_text}")
    elif plan.native_markdown and plan.markdown:
        message += markdown_to_unimessage(plan.markdown)
    elif plan.text:
        message += UniMessage.text(plan.text)
    for image_url in plan.image_urls:
        message += UniMessage.image(url=image_url)
    return message
