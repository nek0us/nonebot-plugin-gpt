"""统一处理 UniMessage 与普通文本的适配器发送边界。"""

from __future__ import annotations

from typing import Any

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna.uniseg import UniMessage


async def finish_message(matcher: Matcher, event: Event, message: Any) -> None:
    """发送跨平台消息后结束当前匹配器。"""
    if isinstance(message, UniMessage):
        await message.send(event)
        await matcher.finish()
        return
    await matcher.finish(message)
