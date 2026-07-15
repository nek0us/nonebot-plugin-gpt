"""统一处理 UniMessage 与普通文本的适配器发送边界。"""

from __future__ import annotations

import asyncio
from typing import Any

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import CustomNode, Reference, UniMessage

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
) -> None:
    """优先以跨平台合并引用发送多张文档图片，失败后逐张发送。"""
    if not images:
        await matcher.finish("暂无可展示内容。")
        return

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
            receipt = await UniMessage(Reference(nodes=nodes)).send(event)
        except Exception as error:
            logger.debug(f"合并引用消息发送失败，改为逐张图片发送：{error}")
        else:
            _schedule_recall(receipt, recall_after)
            await matcher.finish()
            return

    for image in images:
        receipt = await UniMessage.image(raw=image, name="gpt-document.png").send(event)
        _schedule_recall(receipt, recall_after)
    await matcher.finish()


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
