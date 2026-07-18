"""统一处理 UniMessage 与普通文本的适配器发送边界。"""

from __future__ import annotations

import asyncio
from typing import Any

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import (
    CustomNode,
    FallbackStrategy,
    Reference,
    SerializeFailed,
    UniMessage,
)

from .paged_output import TextPages


async def _recall_later(receipt: Any, delay: int) -> None:
    try:
        await receipt.recall(delay=delay)
    except Exception:
        # 消息已被手动删除或适配器临时不支持撤回时，静默降级即可。
        return


def _schedule_recall(receipt: Any, delay: int) -> None:
    if delay > 0 and getattr(receipt, "recallable", False):
        asyncio.create_task(_recall_later(receipt, delay))


def _self_id(event: Event) -> str:
    getter = getattr(event, "get_self_id", None)
    if callable(getter):
        return str(getter() or "0")
    return str(getattr(event, "self_id", "0") or "0")


async def finish_image_pages(
    matcher: Matcher,
    event: Event,
    images: tuple[bytes, ...],
    *,
    title: str,
    recall_after: int = 0,
    finish: bool = True,
) -> bool:
    """优先以跨平台合并引用发送多张文档图片，失败后逐张发送。"""
    if not images:
        if finish:
            await matcher.finish("暂无可展示内容。")
        return False

    if len(images) > 1:
        nodes = [
            CustomNode(
                uid=_self_id(event),
                name=f"{title} · {index}/{len(images)}",
                content=UniMessage.image(raw=image, name="gpt-document.png"),
            )
            for index, image in enumerate(images, start=1)
        ]
        try:
            receipt = await UniMessage(Reference(nodes=nodes)).send(
                event,
                fallback=FallbackStrategy.forbid,
            )
        except SerializeFailed as error:
            # 导出阶段明确说明该适配器不支持合并引用，此时尚未投递，逐张降级是安全的。
            logger.debug(f"合并引用消息不受当前适配器支持，改为逐张图片发送：{error}")
        except Exception as error:
            # send() 同时包含导出、投递和回执。非导出错误可能发生在上游已接收
            # 合并消息之后，继续逐张重试会造成整组图片重复刷屏。
            logger.warning(
                f"合并引用消息发送结果不确定，停止逐张重试以避免重复发送：{error}"
            )
            if finish:
                await matcher.finish()
            return False
        else:
            _schedule_recall(receipt, recall_after)
            if finish:
                await matcher.finish()
            return True

    for image in images:
        receipt = await UniMessage.image(raw=image, name="gpt-document.png").send(event)
        _schedule_recall(receipt, recall_after)
    if finish:
        await matcher.finish()
    return True


async def finish_message(
    matcher: Matcher,
    event: Event,
    message: Any,
    *,
    recall_after: int = 0,
) -> None:
    """发送跨平台消息后结束当前匹配器。"""
    if isinstance(message, TextPages):
        for page in message.pages:
            receipt = await UniMessage.text(page).send(event)
            if len(message.pages) > 1:
                _schedule_recall(receipt, recall_after)
        await matcher.finish()
        return
    if isinstance(message, UniMessage):
        await message.send(event)
        await matcher.finish()
        return
    await matcher.finish(message)
