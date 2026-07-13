"""基于 ChatGPTWeb 公共服务 API 的适配器无关聊天入口。"""

from __future__ import annotations

from typing import Awaitable, Callable

from ChatGPTWeb import ChatRequest, ChatResult, ChatService
from ChatGPTWeb.api import ChatStreamEvent

from .conversation import ConversationKey, ConversationState, ConversationStore


StreamObserver = Callable[[ChatStreamEvent], None | Awaitable[None]]


class ChatRuntime:
    """在不依赖适配器对象的前提下继续并持久化聊天会话。"""

    def __init__(self, service: ChatService, conversations: ConversationStore):
        self._service = service
        self._conversations = conversations

    async def chat(
        self,
        key: ConversationKey,
        prompt: str,
        *,
        model: str | None = None,
        web_search: bool = False,
        deep_research: bool = False,
        on_event: StreamObserver | None = None,
    ) -> ChatResult:
        state = await self._conversations.get(key)
        request = ChatRequest(
            prompt=prompt,
            conversation_id=state.conversation_id,
            parent_message_id=state.parent_message_id,
            model=model or state.model,
            web_search=web_search,
            deep_research=deep_research,
        )
        result = await self._service.stream_to_callback(request, on_event or (lambda _event: None))
        if result.ok:
            await self._conversations.save(
                key,
                ConversationState(
                    conversation_id=result.conversation_id,
                    parent_message_id=result.message_id,
                    model=result.used_model or request.model,
                    metadata={
                        "account": result.account,
                        "usage": result.usage,
                    },
                ),
            )
        return result

    async def reset(self, key: ConversationKey) -> None:
        await self._conversations.clear(key)
