"""连接逻辑会话运行时与跨平台消息输出的应用层。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from ChatGPTWeb import ChatResult
from ChatGPTWeb.config import IOFile
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import UniMessage

from .chat_runtime import ChatRuntime
from .chat_images import render_chat_markdown
from .conversation import ConversationCreator, ConversationKey
from .failure_diagnostics import ChatFailureDiagnostics
from .rendering import build_render_plan
from .unimessage_output import build_unimessage


MarkdownRenderer = Callable[[str], Awaitable[bytes | None]]
DEFAULT_ERROR_MESSAGE = "抱歉，这次没能顺利回应。请稍后再试；若持续发生，请联系机器人管理员。"
DEFAULT_CONVERSATION_RECOVERY_MESSAGE = "当前对话已无法继续，请重新初始化人设后再试。"
DEFAULT_SESSION_REAUTHENTICATION_MESSAGE = "连接正在自动恢复，请稍后再试一次。"
DEFAULT_RATE_LIMIT_MESSAGE = "当前上游服务请求较多，正在等待恢复，请稍后再试。"


# 这两类错误说明逻辑会话绑定的账号已经不再可用。临时未就绪等错误
# 仍应提示稍后重试，避免让用户不必要地重置人设。
_CONVERSATION_RECOVERY_KINDS = {
    "conversation_session_missing",
    "conversation_session_stopped",
}
_SESSION_REAUTHENTICATION_KINDS = {
    "session_reauthentication_pending",
    "session_recovery_timeout",
    "conversation_session_recovery_timeout",
}
_RATE_LIMIT_KINDS = {
    "rate_limited",
    "conversation_rate_limited",
    "capability_rate_limited",
    "conversation_capability_rate_limited",
}


async def _render_markdown(markdown: str) -> bytes | None:
    """使用默认原生主题渲染复杂 Markdown。"""
    return await render_chat_markdown(markdown)


def create_markdown_renderer(template: str, *, font_scale: float = 1.0) -> MarkdownRenderer:
    """绑定配置后的聊天图片主题，供每次对话渲染复用。"""
    async def render(markdown: str) -> bytes | None:
        return await render_chat_markdown(markdown, template=template, font_scale=font_scale)

    return render


def _error_message(
    result: ChatResult,
    error_message: str,
    conversation_recovery_message: str,
    session_reauthentication_message: str,
    rate_limit_message: str,
    failure_diagnostics: ChatFailureDiagnostics | None,
) -> UniMessage:
    """将核心服务的失败结果收敛为不会泄露内部细节的用户提示。"""
    if failure_diagnostics:
        failure_diagnostics.record_result(result)
    error_kinds = {
        str(error.get("kind", ""))
        for error in result.errors
        if isinstance(error, dict)
    }
    if error_kinds & _CONVERSATION_RECOVERY_KINDS:
        return UniMessage.text(conversation_recovery_message)
    if error_kinds & _SESSION_REAUTHENTICATION_KINDS:
        return UniMessage.text(session_reauthentication_message)
    if error_kinds & _RATE_LIMIT_KINDS:
        return UniMessage.text(rate_limit_message)
    return UniMessage.text(error_message)


def _unexpected_error_message(
    operation: str,
    error_message: str,
    failure_diagnostics: ChatFailureDiagnostics | None,
) -> UniMessage:
    """记录管理员可见的异常，避免把堆栈或上游报错直接发送到聊天。"""
    logger.exception(f"GPT {operation} 处理异常")
    if failure_diagnostics:
        failure_diagnostics.record_exception()
    return UniMessage.text(error_message)


async def render_result(
    result: ChatResult,
    *,
    supports_markdown: bool = False,
    render_mode: Literal["auto", "text", "image"] = "auto",
    render_markdown: MarkdownRenderer | None = _render_markdown,
    error_message: str = DEFAULT_ERROR_MESSAGE,
    conversation_recovery_message: str = DEFAULT_CONVERSATION_RECOVERY_MESSAGE,
    session_reauthentication_message: str = DEFAULT_SESSION_REAUTHENTICATION_MESSAGE,
    rate_limit_message: str = DEFAULT_RATE_LIMIT_MESSAGE,
    failure_diagnostics: ChatFailureDiagnostics | None = None,
) -> UniMessage:
    """把结构化聊天结果转换为可由 Alconna 发送的统一消息。"""
    if not result.ok:
        return _error_message(
            result,
            error_message,
            conversation_recovery_message,
            session_reauthentication_message,
            rate_limit_message,
            failure_diagnostics,
        )
    return await build_unimessage(
        build_render_plan(
            result,
            supports_markdown=supports_markdown,
            render_mode=render_mode,
        ),
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
    render_mode: Literal["auto", "text", "image"] = "auto",
    render_markdown: MarkdownRenderer | None = _render_markdown,
    error_message: str = DEFAULT_ERROR_MESSAGE,
    conversation_recovery_message: str = DEFAULT_CONVERSATION_RECOVERY_MESSAGE,
    session_reauthentication_message: str = DEFAULT_SESSION_REAUTHENTICATION_MESSAGE,
    rate_limit_message: str = DEFAULT_RATE_LIMIT_MESSAGE,
    failure_diagnostics: ChatFailureDiagnostics | None = None,
    creator: ConversationCreator | None = None,
) -> UniMessage:
    """处理一条普通聊天消息并返回跨平台输出。"""
    try:
        options = {
            "model": model,
            "prefer_paid_account": prefer_paid_account,
            "files": files,
            "web_search": web_search,
        }
        if creator is not None:
            options["creator"] = creator
        result = await runtime.chat(key, prompt, **options)
    except Exception:
        return _unexpected_error_message("聊天", error_message, failure_diagnostics)
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_mode=render_mode,
        render_markdown=render_markdown,
        error_message=error_message,
        conversation_recovery_message=conversation_recovery_message,
        session_reauthentication_message=session_reauthentication_message,
        rate_limit_message=rate_limit_message,
        failure_diagnostics=failure_diagnostics,
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
    render_mode: Literal["auto", "text", "image"] = "auto",
    render_markdown: MarkdownRenderer | None = _render_markdown,
    error_message: str = DEFAULT_ERROR_MESSAGE,
    conversation_recovery_message: str = DEFAULT_CONVERSATION_RECOVERY_MESSAGE,
    session_reauthentication_message: str = DEFAULT_SESSION_REAUTHENTICATION_MESSAGE,
    rate_limit_message: str = DEFAULT_RATE_LIMIT_MESSAGE,
    failure_diagnostics: ChatFailureDiagnostics | None = None,
    creator: ConversationCreator | None = None,
) -> UniMessage:
    """初始化人设并将结果投影为跨平台输出。"""
    try:
        options = {
            "model": model,
            "prefer_paid_account": prefer_paid_account,
            "continue_existing": continue_existing,
        }
        if creator is not None:
            options["creator"] = creator
        result = await runtime.initialize_persona(key, persona_name, **options)
    except ValueError as error:
        return UniMessage.text(str(error))
    except Exception:
        return _unexpected_error_message("人设初始化", error_message, failure_diagnostics)
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_mode=render_mode,
        render_markdown=render_markdown,
        error_message=error_message,
        conversation_recovery_message=conversation_recovery_message,
        session_reauthentication_message=session_reauthentication_message,
        rate_limit_message=rate_limit_message,
        failure_diagnostics=failure_diagnostics,
    )


async def restart_persona_reply(
    runtime: ChatRuntime,
    key: ConversationKey,
    *,
    supports_markdown: bool = False,
    render_mode: Literal["auto", "text", "image"] = "auto",
    render_markdown: MarkdownRenderer | None = _render_markdown,
    error_message: str = DEFAULT_ERROR_MESSAGE,
    conversation_recovery_message: str = DEFAULT_CONVERSATION_RECOVERY_MESSAGE,
    session_reauthentication_message: str = DEFAULT_SESSION_REAUTHENTICATION_MESSAGE,
    rate_limit_message: str = DEFAULT_RATE_LIMIT_MESSAGE,
    failure_diagnostics: ChatFailureDiagnostics | None = None,
    creator: ConversationCreator | None = None,
) -> UniMessage:
    """重置当前人设并创建新的逻辑会话。"""
    try:
        if creator is None:
            result = await runtime.restart_persona(key)
        else:
            result = await runtime.restart_persona(key, creator=creator)
    except ValueError as error:
        return UniMessage.text(str(error))
    except Exception:
        return _unexpected_error_message("人设重置", error_message, failure_diagnostics)
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_mode=render_mode,
        render_markdown=render_markdown,
        error_message=error_message,
        conversation_recovery_message=conversation_recovery_message,
        session_reauthentication_message=session_reauthentication_message,
        rate_limit_message=rate_limit_message,
        failure_diagnostics=failure_diagnostics,
    )


async def rewind_reply(
    runtime: ChatRuntime,
    key: ConversationKey,
    reference: str,
    *,
    supports_markdown: bool = False,
    render_mode: Literal["auto", "text", "image"] = "auto",
    render_markdown: MarkdownRenderer | None = _render_markdown,
    error_message: str = DEFAULT_ERROR_MESSAGE,
    conversation_recovery_message: str = DEFAULT_CONVERSATION_RECOVERY_MESSAGE,
    session_reauthentication_message: str = DEFAULT_SESSION_REAUTHENTICATION_MESSAGE,
    rate_limit_message: str = DEFAULT_RATE_LIMIT_MESSAGE,
    failure_diagnostics: ChatFailureDiagnostics | None = None,
) -> UniMessage:
    """回退当前逻辑会话的物理上下文。"""
    if not reference.strip():
        return UniMessage.text("请输入要回退到的对话序号或消息标识。")
    try:
        result = await runtime.rewind_visible(key, reference)
    except ValueError as error:
        return UniMessage.text(str(error))
    except Exception:
        return _unexpected_error_message("会话回退", error_message, failure_diagnostics)
    return await render_result(
        result,
        supports_markdown=supports_markdown,
        render_mode=render_mode,
        render_markdown=render_markdown,
        error_message=error_message,
        conversation_recovery_message=conversation_recovery_message,
        session_reauthentication_message=session_reauthentication_message,
        rate_limit_message=rate_limit_message,
        failure_diagnostics=failure_diagnostics,
    )
