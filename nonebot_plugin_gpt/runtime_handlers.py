"""连接逻辑会话运行时与跨平台消息输出的应用层。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ChatGPTWeb import ChatResult
from ChatGPTWeb.config import IOFile
from nonebot_plugin_alconna.uniseg import UniMessage

from .chat_runtime import ChatRuntime
from .conversation import ConversationKey
from .rendering import build_render_plan
from .unimessage_output import build_unimessage


MarkdownRenderer = Callable[[str], Awaitable[bytes | None]]


async def _render_markdown(markdown: str) -> bytes | None:
    """将复杂 Markdown 交给已安装的 HTML 渲染器处理。"""
    from nonebot_plugin_htmlkit import md_to_pic

    return await md_to_pic(markdown, max_width=720)


def _error_message(result: ChatResult) -> UniMessage:
    """将核心服务的失败结果收敛为不会泄露内部细节的用户提示。"""
    if result.text:
        return UniMessage.text(result.text)
    return UniMessage.text("ChatGPT 请求未成功完成，请稍后重试。")


async def render_result(
    result: ChatResult,
    *,
    supports_markdown: bool = False,
    render_markdown: MarkdownRenderer | None = _render_markdown,
) -> UniMessage:
    """把结构化聊天结果转换为可由 Alconna 发送的统一消息。"""
    if not result.ok:
        return _error_message(result)
    return await build_unimessage(
        build_render_plan(result, supports_markdown=supports_markdown),
        render_markdown=render_markdown,
    )


async def chat_reply(
    runtime: ChatRuntime,
    key: ConversationKey,
    prompt: str,
    *,
    model: str | None = None,
    prefer_paid_account: bool | None = None,
    files: list[IOFile] | None = None,
    web_search: bool = True,
    supports_markdown: bool = False,
    render_markdown: MarkdownRenderer | None = _render_markdown,
) -> UniMessage:
    """处理一条普通聊天消息并返回跨平台输出。"""
    result = await runtime.chat(
        key,
        prompt,
        model=model,
        prefer_paid_account=prefer_paid_account,
        files=files,
        web_search=web_search,
    )
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_markdown=render_markdown,
    )


async def persona_reply(
    runtime: ChatRuntime,
    key: ConversationKey,
    persona_name: str,
    *,
    model: str = "auto",
    prefer_paid_account: bool = False,
    continue_existing: bool = False,
    supports_markdown: bool = False,
    render_markdown: MarkdownRenderer | None = _render_markdown,
) -> UniMessage:
    """初始化人设并将结果投影为跨平台输出。"""
    try:
        result = await runtime.initialize_persona(
            key,
            persona_name,
            model=model,
            prefer_paid_account=prefer_paid_account,
            continue_existing=continue_existing,
        )
    except ValueError as error:
        return UniMessage.text(str(error))
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_markdown=render_markdown,
    )


async def restart_persona_reply(
    runtime: ChatRuntime,
    key: ConversationKey,
    *,
    supports_markdown: bool = False,
    render_markdown: MarkdownRenderer | None = _render_markdown,
) -> UniMessage:
    """重置当前人设并创建新的逻辑会话。"""
    try:
        result = await runtime.restart_persona(key)
    except ValueError as error:
        return UniMessage.text(str(error))
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_markdown=render_markdown,
    )


async def rewind_reply(
    runtime: ChatRuntime,
    key: ConversationKey,
    reference: str,
    *,
    supports_markdown: bool = False,
    render_markdown: MarkdownRenderer | None = _render_markdown,
) -> UniMessage:
    """回退当前逻辑会话的物理上下文。"""
    if not reference.strip():
        return UniMessage.text("请输入要回退到的对话序号或消息标识。")
    try:
        result = await runtime.rewind(key, reference)
    except ValueError as error:
        return UniMessage.text(str(error))
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_markdown=render_markdown,
    )
