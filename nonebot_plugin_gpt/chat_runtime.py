"""基于 ChatGPTWeb 公共服务 API 的适配器无关聊天入口。"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Literal

from ChatGPTWeb import AgentService, AgentState, AgentTool, AgentToolResult, AgentTurn, ChatRequest, ChatResult, ChatService, ConversationOperation
from ChatGPTWeb.api import ChatStreamEvent
from ChatGPTWeb.config import IOFile

from .conversation import ConversationKey, ConversationState, ConversationStore
from .context_policy import (
    ContextPolicy,
    build_reinforced_prompt,
    build_restart_prompt,
    build_summary_prompt,
    decide_context_maintenance,
)
from .history_views import HistoryProjection, project_history


StreamObserver = Callable[[ChatStreamEvent], None | Awaitable[None]]
RenderMode = Literal["auto", "text", "image"]
_RENDER_MODES = frozenset({"auto", "text", "image"})


class ChatRuntime:
    """在不依赖适配器对象的前提下继续并持久化聊天会话。"""

    def __init__(
        self,
        service: ChatService,
        conversations: ConversationStore,
        context_policy: ContextPolicy | None = None,
    ):
        self._service = service
        self._conversations = conversations
        self._context_policy = context_policy or ContextPolicy()
        self._conversation_locks: dict[str, asyncio.Lock] = {}

    def _conversation_lock(self, key: ConversationKey) -> asyncio.Lock:
        """同一逻辑会话的上游请求必须按顺序提交，避免父消息分叉。"""
        return self._conversation_locks.setdefault(key.value, asyncio.Lock())

    async def chat(
        self,
        key: ConversationKey,
        prompt: str,
        *,
        model: str | None = None,
        prefer_paid_account: bool | None = None,
        files: list[IOFile] | None = None,
        web_search: bool = False,
        deep_research: bool = False,
        on_event: StreamObserver | None = None,
    ) -> ChatResult:
        async with self._conversation_lock(key):
            return await self._chat_locked(
                key,
                prompt,
                model=model,
                prefer_paid_account=prefer_paid_account,
                files=files,
                web_search=web_search,
                deep_research=deep_research,
                on_event=on_event,
            )

    async def agent_turn(
        self,
        key: ConversationKey,
        task: str,
        tools: list[AgentTool],
        *,
        state: AgentState | None = None,
        tool_result: AgentToolResult | None = None,
        model: str = "auto",
    ) -> AgentTurn:
        """在独立的控制会话中执行一轮受控智能体决策。

        工具协议不能和角色扮演正文共用物理会话：人设会自然优先输出日常
        对话，而不是严格 JSON，且协议消息也不应污染用户的聊天记录。Agent
        游标只由 ``AgentState`` 持有；普通逻辑会话始终保留自己的位置。
        """
        async with self._conversation_lock(key):
            conversation = await self._conversations.get(key)
            selected_model = model if model and model != "auto" else (conversation.model or "auto")
            cursor = state or AgentState(model=selected_model)
            return await AgentService(self._service).turn(
                task,
                tools,
                state=cursor,
                tool_result=tool_result,
                model=selected_model,
                continue_existing=False,
            )

    async def render_agent_final(
        self,
        key: ConversationKey,
        task: str,
        agent_answer: str,
        *,
        model: str = "auto",
    ) -> str:
        """让已有角色以自然口吻呈现已完成的受控任务结果。"""
        async with self._conversation_lock(key):
            state = await self._conversations.get(key)
            if not state.conversation_id:
                return agent_answer
            prompt = "\n".join((
                "【已完成的受控任务】",
                "下面是可信的任务完成结果。请按当前人设自然回复用户，",
                "不要提及 JSON、协议、工具调用或内部执行过程；不要重复执行任务。",
                f"用户原任务：{task}",
                f"完成结果：{agent_answer}",
            ))
            result = await self._chat_locked(key, prompt, model=model or state.model)
            return result.text if result.ok and result.text.strip() else agent_answer

    async def _chat_locked(
        self,
        key: ConversationKey,
        prompt: str,
        *,
        model: str | None = None,
        prefer_paid_account: bool | None = None,
        files: list[IOFile] | None = None,
        web_search: bool = False,
        deep_research: bool = False,
        on_event: StreamObserver | None = None,
    ) -> ChatResult:
        state = await self._conversations.get(key)
        if not state.label:
            state.label = self._build_session_label(prompt)
        use_paid_account = (
            bool(state.metadata.get("prefer_paid_account", False))
            if prefer_paid_account is None
            else prefer_paid_account
        )
        request = ChatRequest(
            prompt=prompt,
            conversation_id=state.conversation_id,
            parent_message_id=state.parent_message_id,
            model=model or state.model,
            prefer_paid_account=use_paid_account,
            files=(files or []).copy(),
            web_search=web_search,
            deep_research=deep_research,
        )
        result = await self._chat_with_context_maintenance(
            key,
            state,
            request,
            on_event or (lambda _event: None),
        )
        if result.ok:
            state.conversation_id = result.conversation_id
            state.parent_message_id = result.message_id
            state.model = result.used_model or request.model
            state.metadata.update({
                "account": result.account,
                "usage": result.usage,
                "prefer_paid_account": use_paid_account,
            })
            await self._conversations.save(key, state)
        return result

    @staticmethod
    def _build_session_label(prompt: str) -> str:
        """从首条用户消息生成简短的默认逻辑会话名称。"""
        normalized = " ".join(prompt.split())
        return normalized[:28] or "未命名会话"

    async def _chat_with_context_maintenance(
        self,
        key: ConversationKey,
        state: ConversationState,
        request: ChatRequest,
        on_event: StreamObserver,
    ) -> ChatResult:
        if not state.conversation_id:
            return await self._service.stream_to_callback(request, on_event)

        estimate = await self._service.estimate_context(
            state.conversation_id,
            model=state.model,
            account=str(state.metadata.get("account", "")),
        )
        decision = decide_context_maintenance(
            estimated_tokens=estimate.estimated_tokens,
            context_window_tokens=estimate.context_window_tokens,
            policy=self._context_policy,
            has_persona=bool(state.persona_prompt),
        )
        if not decision.compact:
            return await self._service.stream_to_callback(request, on_event)

        if self._context_policy.mode == "reinforce":
            request.prompt = build_reinforced_prompt(state.persona_prompt, request.prompt)
            return await self._service.stream_to_callback(request, on_event)

        summary = await self._service.send(ChatRequest(
            prompt=build_summary_prompt(),
            conversation_id=state.conversation_id,
            parent_message_id=state.parent_message_id,
            model=state.model,
        ))
        if not summary.ok or not summary.text:
            return await self._service.stream_to_callback(request, on_event)

        restart_request = ChatRequest(
            prompt=build_restart_prompt(state.persona_prompt, summary.text, request.prompt),
            model=request.model,
            prefer_paid_account=request.prefer_paid_account,
            files=request.files.copy(),
            web_search=request.web_search,
            deep_research=request.deep_research,
        )
        result = await self._service.stream_to_callback(restart_request, on_event)
        if result.ok:
            await self._conversations.add_checkpoint(
                key,
                state,
                conversation_id=result.conversation_id,
                parent_message_id=result.message_id,
                model=result.used_model or restart_request.model,
                summary=summary.text,
            )
        return result

    async def create_session(self, key: ConversationKey, label: str = "") -> ConversationState:
        """创建并切换到一条用户可见的逻辑会话。"""
        return await self._conversations.create(key, label)

    async def initialize_persona(
        self,
        key: ConversationKey,
        persona_name: str,
        *,
        model: str = "auto",
        prefer_paid_account: bool = False,
        continue_existing: bool = False,
    ) -> ChatResult:
        """初始化人设，并保存自动压缩所需的人设提示词快照。"""
        persona_prompt = await self._service.get_persona_prompt(persona_name)
        if not persona_prompt:
            raise ValueError("未找到指定人设")
        state = await self._conversations.get(key) if continue_existing else await self.create_session(key, persona_name)
        result = await self._service.send(ChatRequest(
            prompt=persona_name,
            conversation_id=state.conversation_id if continue_existing else "",
            parent_message_id=state.parent_message_id if continue_existing else "",
            model=model or state.model,
            prefer_paid_account=prefer_paid_account,
            operation=ConversationOperation.START_PERSONA,
        ))
        if result.ok:
            state.persona_name = persona_name
            state.persona_prompt = persona_prompt
            state.conversation_id = result.conversation_id
            state.parent_message_id = result.message_id
            state.model = result.used_model or model or state.model
            state.metadata.update({
                "account": result.account,
                "usage": result.usage,
                "prefer_paid_account": prefer_paid_account,
            })
            await self._conversations.save(key, state)
        return result

    async def list_sessions(self, key: ConversationKey) -> list[ConversationState]:
        """列出当前用户在本会话范围内可切换的逻辑会话。"""
        return await self._conversations.list(key)

    async def get_active_session(self, key: ConversationKey) -> ConversationState:
        """获取当前会话范围绑定的逻辑会话。"""
        return await self._conversations.get(key)

    async def get_render_mode(
        self,
        key: ConversationKey,
        default_mode: RenderMode,
    ) -> tuple[RenderMode, bool]:
        """读取当前访问范围的输出偏好，并在未覆盖时回退到全局默认值。"""
        value = await self._conversations.get_preference(key, "render_mode")
        if value in _RENDER_MODES:
            return value, True
        return default_mode, False

    async def set_render_mode(self, key: ConversationKey, mode: RenderMode | None) -> None:
        """设置当前访问范围的输出偏好；None 表示恢复全局默认值。"""
        await self._conversations.set_preference(key, "render_mode", mode)

    async def set_model_preference(
        self,
        key: ConversationKey,
        model: str,
        *,
        prefer_paid_account: bool,
    ) -> ConversationState:
        """更新当前逻辑会话的模型偏好，不改变其已有上下文。"""
        state = await self._conversations.get(key)
        state.model = model
        state.metadata["prefer_paid_account"] = prefer_paid_account
        return await self._conversations.save(key, state)

    async def get_history(self, key: ConversationKey) -> list[dict[str, str]]:
        """获取当前逻辑会话活动检查点的问答历史。"""
        state = await self._conversations.get(key)
        if not state.conversation_id:
            return []
        return await self._service.get_history(state.conversation_id)

    async def get_visible_history(self, key: ConversationKey) -> HistoryProjection:
        """获取可安全展示给会话成员的历史记录。"""
        state = await self._conversations.get(key)
        if not state.conversation_id:
            return HistoryProjection((), ())
        history = await self._service.get_history(state.conversation_id)
        return project_history(
            history,
            persona_prompt=state.persona_prompt,
            hide_initial=bool(state.persona_name),
        )

    async def switch_session(self, key: ConversationKey, logical_id: str) -> ConversationState:
        """切换逻辑会话，而不是切到自动压缩产生的检查点。"""
        return await self._conversations.switch(key, logical_id)

    async def restart_persona(self, key: ConversationKey) -> ChatResult:
        """以当前逻辑会话的人设开始一段新的逻辑会话。"""
        state = await self._conversations.get(key)
        if not state.persona_name:
            raise ValueError("当前逻辑会话没有已初始化的人设")
        return await self.initialize_persona(
            key,
            state.persona_name,
            model=state.model,
            prefer_paid_account=bool(state.metadata.get("prefer_paid_account", False)),
            continue_existing=False,
        )

    async def rewind(self, key: ConversationKey, reference: str) -> ChatResult:
        """在当前逻辑会话的活动物理检查点内回退到指定位置。"""
        state = await self._conversations.get(key)
        if not state.conversation_id:
            raise ValueError("当前逻辑会话尚未开始聊天")
        result = await self._service.send(ChatRequest(
            prompt="",
            conversation_id=state.conversation_id,
            parent_message_id=state.parent_message_id,
            model=state.model,
            operation=ConversationOperation.REWIND,
            reference=reference,
        ))
        if result.ok:
            state.conversation_id = result.conversation_id or state.conversation_id
            state.parent_message_id = result.message_id or state.parent_message_id
            state.model = result.used_model or state.model
            state.metadata.update({"account": result.account, "usage": result.usage})
            await self._conversations.save(key, state)
        return result

    async def rewind_visible(self, key: ConversationKey, reference: str) -> ChatResult:
        """按历史聊天展示的轮次回退，同时兼容关键词和底层消息标识。"""
        if not reference.strip().isdecimal():
            return await self.rewind(key, reference)
        projection = await self.get_visible_history(key)
        return await self.rewind(key, projection.resolve_rewind_reference(reference))
