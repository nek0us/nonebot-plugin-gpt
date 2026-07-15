"""统一处理 UniMessage 与普通文本的适配器发送边界。"""

from __future__ import annotations

import asyncio
from typing import Any

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna.uniseg import UniMessage

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
