"""首次聊天时按会话范围自动加载默认人设。"""

from __future__ import annotations

import asyncio

from ChatGPTWeb import ChatResult

from .chat_runtime import ChatRuntime
from .conversation import ConversationCreator, ConversationKey


class AutoPersonaInitializer:
    """将旧的入群/好友初始化语义映射到新的逻辑会话。"""

    def __init__(
        self,
        runtime: ChatRuntime,
        *,
        group_enabled: bool = False,
        friend_enabled: bool = False,
        group_persona_name: str = "",
        friend_persona_name: str = "",
    ):
        self._runtime = runtime
        self._group_enabled = group_enabled
        self._friend_enabled = friend_enabled
        self._group_persona_name = group_persona_name.strip()
        self._friend_persona_name = friend_persona_name.strip()
        self._locks: dict[str, asyncio.Lock] = {}

    def persona_for_scope(self, *, is_shared: bool) -> str:
        if is_shared and self._group_enabled:
            return self._group_persona_name
        if not is_shared and self._friend_enabled:
            return self._friend_persona_name
        return ""

    async def ensure_initialized(
        self,
        key: ConversationKey,
        *,
        is_shared: bool,
        model: str,
        prefer_paid_account: bool,
        creator: ConversationCreator | None = None,
    ) -> ChatResult | None:
        """仅在用户尚未开始逻辑会话时初始化，避免覆盖手动选择。"""
        persona_name = self.persona_for_scope(is_shared=is_shared)
        if not persona_name:
            return None
        lock = self._locks.setdefault(key.value, asyncio.Lock())
        try:
            async with lock:
                state = await self._runtime.get_active_session(key)
                if state.conversation_id or state.persona_name:
                    return None
                try:
                    return await self._runtime.initialize_persona(
                        key,
                        persona_name,
                        model=model,
                        prefer_paid_account=prefer_paid_account,
                        creator=creator,
                    )
                except ValueError:
                    # 配置的人设尚未创建或已删除时，直接让用户首条消息创建无
                    # 人设会话；不能用默认人设悄悄改变用户的对话语境。
                    return None
        finally:
            if not lock.locked():
                self._locks.pop(key.value, None)
