from ChatGPTWeb import AgentAnchorPolicy, AgentSafetyPolicy, ChatService, chatgpt
from ChatGPTWeb.config import Personality
from nonebot.log import logger
from nonebot import on_message
from nonebot.matcher import Matcher
from nonebot.params import Arg
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot import get_driver
from nonebot_plugin_alconna import Match, on_alconna
from nonebot_plugin_alconna.uniseg import At, OriginalUniMsg, Target, UniMessage, get_target
from importlib.metadata import version
import asyncio
import inspect
import json
from pathlib import Path
from time import time


from .config import config_gpt, config_nb, Config
from .source import (
    ban_str_path,
    banpath,
    cdk_registry_path,
    conversation_store_path,
    data_dir,
    agent_schedule_path,
    legacy_cdk_list_path,
    legacy_cdk_source_path,
    personpath,
    plusstatus,
    whitepath,
)
from .agent_runtime import AgentAccess, create_agent_runtime
from .agent_commands import CommandRunner
from .agent_filesystem import AgentFilesystemScanner
from .agent_readonly import AgentReadonlyRoots
from .agent_sandbox import SandboxError, WorkspaceSandbox
from .agent_skills import load_command_skill_sources
from .agent_scheduler import AgentScheduler, ScheduledReminder
from .agent_web import WorkspaceWebRenderer
from .agent_workspace import AgentWorkspace
from .managed_services import ManagedServiceRegistry
from .check import add_personal_white, add_white, del_personal_white, del_white, get_access_session_id, get_event_user_id, get_event_user_identity, gpt_agent_rule, gpt_cdk_redeem_rule, gpt_command_rule, gpt_manage_rule, gpt_operator_command_rule, gpt_persona_editor_rule, gpt_rule, gpt_superuser_rule, plus_status, read_whitelist
from .cdk import CdkRegistry
from .command_compat import (
    build_legacy_command,
    command_argument_text,
    is_registered_command_text,
    preferred_address_prefix,
)
from .chat_runtime import ChatRuntime
from .context_policy import ContextPolicy
from .conversation import ConversationCreator, ConversationKey, ConversationStore
from .runtime_handlers import create_markdown_renderer, chat_reply, continue_previous_chapter_reply, context_status_reply, new_conversation_reply, persona_reply, restart_persona_reply, rewind_reply
from .session_commands import list_sessions, switch_session
from .model_selection import resolve_paid_model, select_model
from .attachments import extract_upload_files
from .auto_persona import AutoPersonaInitializer
from .chat_input import attachment_segment_counts, build_chat_prompt, extract_chat_message
from .persona_views import list_personas, show_persona
from .persona_editor import (
    PersonaValidationError,
    extract_text,
    parse_r18,
    parse_visibility,
    validate_name,
    validate_value,
)
from .history_views import format_history, parse_history_view_argument
from .native_markdown import supports_native_markdown
from .help_views import format_help
from .management_views import format_account_status
from .management_images import build_account_status_html, build_help_html, render_management_image
from .message_output import finish_image_pages, finish_message
from .failure_diagnostics import ChatFailureDiagnostics
from .access_views import format_bans, format_whitelist, parse_access_target
from .paged_output import paginate_text
from .document_output import (
    HistoryPage,
    build_history_pages,
    markdown_pages_from_text,
    render_history_pages,
    render_markdown_pages,
)
from .table_documents import (
    blacklist_table_pages,
    cdk_table_pages,
    persona_table_pages,
    render_table_pages,
    session_table_pages,
    TablePage,
    whitelist_table_pages,
)
from .plus_views import grant_paid_access, revoke_paid_access, set_global_paid_enabled
from .personality_service import ensure_default_persona
from .persona_migration import migrate_legacy_personas
from .remote_service import RemoteChatService
from .event_scope import (
    format_group_speaker_prompt,
    resolve_event_scope,
    resolve_participant_display_name,
    resolve_participant_identity,
)
from .group_context import (
    GroupContextBuffer,
    GroupContextSelection,
    format_recent_group_context,
    prepend_recent_group_context,
)


cdk_registry = CdkRegistry(
    cdk_registry_path,
    legacy_list_path=legacy_cdk_list_path,
    legacy_source_path=legacy_cdk_source_path,
)
chat_markdown_renderer = create_markdown_renderer(
    config_gpt.gpt_chat_image_template,
    font_scale=config_gpt.gpt_image_font_scale,
)
agent_safety_policy = AgentSafetyPolicy(
    enabled=config_gpt.gpt_agent_sensitive_task_guard,
    extra_blocked_terms=tuple(config_gpt.gpt_agent_sensitive_terms),
    refusal_message=config_gpt.gpt_agent_sensitive_task_message,
)
agent_anchor_policy = AgentAnchorPolicy(
    enabled=config_gpt.gpt_agent_anchor_sessions,
)


def legacy_command(name, aliases=None, rule=None, priority=1, block=False):
    """用 Alconna 解析旧指令，保持原有名称、别名和规则不变。"""
    if rule is gpt_rule:
        rule = gpt_command_rule
    address_prefixes = [
        *getattr(config_nb, "nickname", []),
        *config_gpt.gpt_chat_start,
    ]
    return on_alconna(
        build_legacy_command(name, aliases, address_prefixes),
        rule=rule,
        use_cmd_start=True,
        use_cmd_sep=True,
        priority=priority,
        block=block,
    )


def _argument_text(argument: Match[object]) -> str:
    """将 Alconna 的可选参数统一为旧命令处理器使用的文本。"""
    if not argument.available:
        return ""
    return command_argument_text(argument.result)


def _redeem_command(code: str) -> str:
    """生成可直接复制的 CDK 兑换命令。"""
    nickname = preferred_address_prefix(getattr(config_nb, "nickname", []))
    return f"{nickname} 兑换 {code}" if nickname else f"@机器人 兑换 {code}"


def _is_reply_event(event: Event) -> bool:
    """读取适配器可选的回复标记。"""
    return bool(getattr(event, "reply", None))


def _is_group_context(event: Event) -> bool:
    """识别群组、频道等多人会话。"""
    return resolve_event_scope(event).is_shared


def _is_group_admin(event: Event) -> bool:
    """仅在适配器明确给出 owner/admin 身份时允许 R18 群聊初始化。"""
    sender = getattr(event, "sender", None)
    return getattr(sender, "role", "member") in {"owner", "admin"}


def _agent_mention_context(message: OriginalUniMsg, *, self_id: str) -> tuple[tuple[str, ...], str]:
    """提取本条 Agent 命令的真实 @ 目标，供超级用户受控提醒使用。"""
    try:
        segments = UniMessage.of(message)
    except Exception:
        return (), ""
    targets: list[tuple[str, str]] = []
    for segment in segments:
        if not isinstance(segment, At) or segment.flag != "user":
            continue
        identifier = str(segment.target).strip()
        if not identifier or identifier == str(self_id).strip():
            continue
        display = " ".join((segment.display or "").split()) or identifier
        if identifier not in {item[0] for item in targets}:
            targets.append((identifier, display))
    if not targets:
        return (), ""
    lines = [
        "【本条消息的提及对象】",
        "以下 ID 来自实际 @ 提及；如任务要求提醒其中一人，只能使用这些 ID 作为“安排指定提醒”的对象ID。",
        *(f"- {display}：{identifier}" for identifier, display in targets),
    ]
    return tuple(identifier for identifier, _ in targets), "\n".join(lines)


async def _finish_management_message(matcher: Matcher, event: Event, message) -> None:
    """发送非聊天的分页信息，并按配置尽力撤回过长输出。"""
    await finish_message(
        matcher,
        event,
        message,
        recall_after=config_gpt.gpt_management_recall_after,
    )


async def _finish_management_image(
    matcher: Matcher,
    event: Event,
    *,
    html: str,
    fallback: str,
) -> None:
    """优先发送管理图片；渲染器异常时保留跨平台文本降级。"""
    try:
        image = await render_management_image(html, font_scale=config_gpt.gpt_image_font_scale)
    except Exception as error:
        logger.warning(f"管理图片渲染失败，已回退文本输出：{error}")
        await _finish_management_message(matcher, event, paginate_text(fallback))
        return
    await finish_message(matcher, event, image)


async def _finish_management_document(
    matcher: Matcher,
    event: Event,
    *,
    title: str,
    pages: tuple[str, ...],
    fallback: str,
) -> None:
    """将较长的管理信息渲染为 Markdown 图片，保留文本降级路径。"""
    try:
        images = await render_markdown_pages(pages, font_scale=config_gpt.gpt_image_font_scale)
    except Exception as error:
        logger.warning(f"管理文档图片渲染失败，已回退文本输出：{error}")
        await _finish_management_message(matcher, event, paginate_text(fallback))
        return
    await finish_image_pages(
        matcher,
        event,
        images,
        title=title,
        recall_after=config_gpt.gpt_management_recall_after,
    )


async def _finish_history_document(
    matcher: Matcher,
    event: Event,
    *,
    pages: tuple[HistoryPage, ...],
    fallback: str,
) -> None:
    """以区分发言角色的卡片样式发送聊天历史。"""
    try:
        images = await render_history_pages(pages, font_scale=config_gpt.gpt_image_font_scale)
    except Exception as error:
        logger.warning(f"聊天记录图片渲染失败，已回退文本输出：{error}")
        await _finish_management_message(matcher, event, paginate_text(fallback))
        return
    await finish_image_pages(
        matcher,
        event,
        images,
        title="聊天记录",
        recall_after=config_gpt.gpt_management_recall_after,
        finish=False,
    )
    await matcher.finish()


async def _finish_management_table(
    matcher: Matcher,
    event: Event,
    *,
    title: str,
    pages: tuple[TablePage, ...],
    fallback: str,
) -> None:
    """将结构化管理数据渲染为分页表格图片。"""
    try:
        images = await render_table_pages(pages, font_scale=config_gpt.gpt_image_font_scale)
    except Exception as error:
        logger.warning(f"管理表格图片渲染失败，已回退文本输出：{error}")
        await _finish_management_message(matcher, event, paginate_text(fallback))
        return
    await finish_image_pages(
        matcher,
        event,
        images,
        title=title,
        recall_after=config_gpt.gpt_management_recall_after,
    )


try:
    __version__ = version("nonebot_plugin_gpt")
except Exception:
    __version__ = None
    
    

__plugin_meta__ = PluginMetadata(
    name="ChatGPT 聊天",
    description="通过浏览器使用 ChatGPT，基于 Alconna 与 UniMessage 提供跨平台聊天能力",
    usage="""
聊天：@机器人或配置的前缀后发送内容。
所有命令同样需要先 @机器人，或以 NICKNAME / gpt_chat_start 中配置的名称开头。
会话：初始化、人设列表、历史聊天、历史会话、切换会话、重置、回到过去。
管理：工作状态、黑名单列表、解黑、白名单列表、添加白名单、删除白名单、会话标识。
授权：生成cdk、生成个人cdk、兑换、cdk列表、作废cdk、退出白名单、退出个人白名单。
付费模型：添加plus、删除plus、plus切换、全局plus。

白名单、Plus 与管理会话均使用插件生成的访问范围标识；管理员可在目标会话执行“会话标识”后复制使用。
    """,
    type="application",
    config=Config,
    homepage="https://github.com/nek0us/nonebot-plugin-gpt",
    extra={
        "author":"nek0us",
        "version":__version__,
    }
)

if isinstance(config_gpt.gpt_session, list):
    migrated_personas = migrate_legacy_personas(data_dir)
    remote_core = config_gpt.gpt_core_mode == "remote"
    if remote_core:
        chatbot = RemoteChatService(
            config_gpt.gpt_core_base_url,
            config_gpt.gpt_core_api_key,
            timeout_seconds=config_gpt.gpt_core_request_timeout,
            personas=migrated_personas,
            max_output_file_size=config_gpt.gpt_file_max_size,
            max_output_total_size=config_gpt.gpt_attachment_max_total_size,
            max_output_file_count=config_gpt.gpt_attachment_max_count,
        )
        chat_service = chatbot
    else:
        personality = Personality([])
        embedded_options = {
            "sessions": config_gpt.gpt_session,
            "plugin": True,
            "storage_dir": data_dir / "chatgptweb",
            "proxy": config_gpt.gpt_proxy,
            "begin_sleep_time": config_gpt.gpt_begin_sleep_time,
            "personality": personality,
            "save_screen": config_gpt.gpt_save_screen,
            "headless": config_gpt.gpt_headless,
            "local_js": config_gpt.gpt_local_js,
            "ready_timeout": config_gpt.gpt_session_recovery_wait_timeout,
            "chat_rate_limit_cooldown_seconds": config_gpt.gpt_chat_rate_limit_cooldown_seconds,
            "account_selection_strategy": config_gpt.gpt_account_selection_strategy,
            "account_selection_window_seconds": config_gpt.gpt_account_selection_window_seconds,
            "control_host": config_gpt.gpt_control_host,
            "control_port": config_gpt.gpt_control_port,
            "control_api_key": config_gpt.gpt_control_api_key,
        }
        output_options = {
            "output_file_max_size": config_gpt.gpt_file_max_size,
            "output_file_max_total_size": config_gpt.gpt_attachment_max_total_size,
            "output_file_max_count": config_gpt.gpt_attachment_max_count,
        }
        capability_quota_options = {
            "capability_quota_enabled": config_gpt.gpt_capability_quota_enabled,
            "free_upload_daily_limit": config_gpt.gpt_free_upload_daily_limit,
            "free_image_generation_daily_limit": (
                config_gpt.gpt_free_image_generation_daily_limit
                if config_gpt.gpt_free_image_generation_daily_limit is not None
                else config_gpt.gpt_free_image_generation_window_limit
            ),
            "free_image_generation_window_limit": (
                config_gpt.gpt_free_image_generation_daily_limit
                if config_gpt.gpt_free_image_generation_daily_limit is not None
                else config_gpt.gpt_free_image_generation_window_limit
            ),
            "free_image_generation_window_seconds": (
                config_gpt.gpt_free_image_generation_window_seconds
            ),
            "capability_rate_limit_cooldown_seconds": (
                config_gpt.gpt_capability_rate_limit_cooldown_seconds
            ),
        }
        core_parameters = inspect.signature(chatgpt).parameters
        embedded_options.update({
            name: value
            for name, value in {
                **output_options,
                **capability_quota_options,
                "project_auto_create": config_gpt.gpt_project_auto_create,
            }.items()
            if name in core_parameters
        })
        chatbot = chatgpt(
            **embedded_options,
        )
        chat_service = ChatService(chatbot)
    failure_diagnostics = ChatFailureDiagnostics()
    chat_runtime = ChatRuntime(
        chat_service,
        ConversationStore(conversation_store_path),
        ContextPolicy(
            mode=config_gpt.gpt_context_compaction_mode,
            utilization_threshold=config_gpt.gpt_context_compaction_threshold,
            minimum_estimated_tokens=config_gpt.gpt_context_compaction_min_tokens,
            fallback_context_window_tokens=config_gpt.gpt_context_compaction_fallback_window_tokens,
            maximum_estimated_tokens=config_gpt.gpt_context_compaction_max_estimated_tokens,
        ),
        agent_safety_policy=agent_safety_policy,
        agent_anchor_policy=agent_anchor_policy,
        conversation_project=config_gpt.gpt_chat_project,
        agent_project=config_gpt.gpt_agent_project,
        persona_projects=config_gpt.gpt_persona_projects,
    )

    async def deliver_scheduled_reminder(item: ScheduledReminder) -> None:
        """在异步事件到期后回到原逻辑会话，交给当前人设自然提醒。"""
        key = ConversationKey(item.conversation_session_id, item.conversation_user_id)
        prompt = (
            "【异步事件】你之前为当前用户安排的一次提醒现在到时。"
            "请按照当前人设自然地提醒对方，不要提及智能体、工具、系统事件或内部实现。"
            f"\n提醒内容：{item.content}"
        )
        if item.speaker_context:
            prompt = f"{prompt}\n{item.speaker_context}"
        message = await chat_reply(
            chat_runtime,
            key,
            prompt,
            supports_markdown=False,
            render_mode=config_gpt.gpt_render_mode,
            render_markdown=chat_markdown_renderer,
            error_message=config_gpt.gpt_error_message,
            conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
            session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
            rate_limit_message=config_gpt.gpt_rate_limit_message,
            image_generation_failure_message=config_gpt.gpt_image_generation_failure_message,
            file_failure_message=config_gpt.gpt_file_failure_message,
            failure_diagnostics=failure_diagnostics,
        )
        await message.send(Target.load(item.target), at_sender=item.user_id or False)

    agent_scheduler = AgentScheduler(agent_schedule_path, deliver_scheduled_reminder)

    async def schedule_agent_reminder(run, delay_seconds: int, content: str) -> str:
        if run.conversation_key is None or not run.delivery_target:
            return "当前消息没有可用于后续投递的跨平台目标，未安排提醒。"
        existing = await agent_scheduler.list_for_user(
            user_id=run.operator_id,
            conversation_session_id=run.conversation_key.session_id,
        )
        if run.access is AgentAccess.MEMBER:
            if len(existing) >= config_gpt.gpt_agent_member_reminder_limit:
                return "当前聊天中你尚未到期的提醒较多，请先取消或等待其中一条完成后再安排。"
            scope_items = await agent_scheduler.list()
            if sum(item.conversation_session_id == run.conversation_key.session_id for item in scope_items) >= config_gpt.gpt_agent_member_scope_reminder_limit:
                return "当前聊天范围待投递的提醒较多，请稍后再试。"
        item = await agent_scheduler.schedule(
            delay_seconds=delay_seconds,
            target=run.delivery_target,
            conversation_session_id=run.conversation_key.session_id,
            conversation_user_id=run.conversation_key.user_id,
            user_id=run.delivery_user_id,
            content=content,
            owner_id=run.operator_id,
            speaker_context=run.agent_context,
        )
        return f"提醒已安排，编号：{item.id}，将在约 {delay_seconds} 秒后投递。"

    async def schedule_target_agent_reminder(run, delay_seconds: int, content: str, target_user_id: str) -> str:
        if run.conversation_key is None or not run.delivery_target:
            return "当前消息没有可用于后续投递的跨平台目标，未安排提醒。"
        item = await agent_scheduler.schedule(
            delay_seconds=delay_seconds,
            target=run.delivery_target,
            conversation_session_id=run.conversation_key.session_id,
            conversation_user_id=run.conversation_key.user_id,
            user_id=target_user_id,
            content=content,
            owner_id=run.operator_id,
            speaker_context=run.agent_context,
        )
        return f"已为指定成员安排提醒，编号：{item.id}，将在约 {delay_seconds} 秒后投递。"

    async def operate_agent_reminder(run, operation: str, identifier: str) -> str:
        if run.conversation_key is None or not run.delivery_user_id:
            return "当前消息没有可用于管理提醒的身份信息。"
        if operation == "list":
            items = await agent_scheduler.list_for_user(
                user_id=run.operator_id,
                conversation_session_id=run.conversation_key.session_id,
            )
            if not items:
                return "当前聊天范围没有你创建的待提醒事项。"
            return "\n".join([
                "你的待提醒事项",
                *(f"- {item.id}：约 {max(0, int(item.due_at - time()))} 秒后提醒“{item.content[:120]}”" for item in items),
            ])
        if operation == "cancel":
            cancelled = await agent_scheduler.cancel_for_user(
                identifier,
                user_id=run.operator_id,
                conversation_session_id=run.conversation_key.session_id,
            )
            return "提醒已取消。" if cancelled else "未找到可取消的提醒；只能取消你在当前聊天范围创建的未到期提醒。"
        return "不支持的提醒操作。"

    async def render_agent_final(run, answer: str):
        if run.conversation_key is None:
            text = answer
        else:
            text = await chat_runtime.render_agent_final(
                run.conversation_key,
                run.task,
                answer,
                model=run.model,
                speaker_context=run.agent_context,
            )
        if not run.artifacts:
            return text
        message = UniMessage.text(text)
        for artifact in run.artifacts:
            name = Path(artifact.path).name
            if artifact.media_type.startswith("image/"):
                message += UniMessage.image(raw=artifact.content, name=name)
            else:
                message += UniMessage.file(raw=artifact.content, name=name)
        return message

    managed_services = ManagedServiceRegistry.from_config(config_gpt.gpt_agent_managed_services)
    for issue in managed_services.configuration_issues:
        logger.warning(f"智能体受管服务配置：{issue}")
    command_runner = None
    command_skills = ()
    if config_gpt.gpt_agent_command_enabled:
        command_runner = CommandRunner(
            default_timeout_seconds=config_gpt.gpt_agent_command_timeout,
            working_directory=config_gpt.gpt_agent_command_workdir,
        )
        skill_load = load_command_skill_sources(
            config_gpt.gpt_agent_command_skills,
            config_gpt.gpt_agent_skill_files,
            command_runner,
        )
        command_skills = skill_load.skills
        logger.warning("已启用智能体系统命令工具；是否逐次确认由 gpt_agent_approval_mode 决定")
        if command_skills:
            logger.warning(f"已加载 {len(command_skills)} 个管理员配置的智能体命令技能")
        for issue in skill_load.issues:
            logger.warning(f"智能体命令技能配置：{issue}")
    elif config_gpt.gpt_agent_command_skills or config_gpt.gpt_agent_skill_files:
        logger.warning("已配置智能体命令技能，但 gpt_agent_command_enabled 为 false，技能不会注册")
    readonly_sources = AgentReadonlyRoots(config_gpt.gpt_agent_read_roots)
    filesystem_scanner = None
    if config_gpt.gpt_agent_filesystem_scan_enabled:
        # A named read-only diagnostic root is already an administrator-approved
        # directory. Reuse it for size scans so a model can scan "运行日志"
        # without confusing it with a broader filesystem root.
        scan_roots = [
            *config_gpt.gpt_agent_filesystem_roots,
            *config_gpt.gpt_agent_read_roots,
        ]
        filesystem_scanner = AgentFilesystemScanner(scan_roots)
        if filesystem_scanner.root_choices:
            logger.warning("已启用智能体目录占用扫描；每次扫描仍需要超级用户在原聊天范围确认")
        else:
            logger.warning("已启用 gpt_agent_filesystem_scan_enabled，但未找到有效的 gpt_agent_filesystem_roots")
    if readonly_sources.root_choices:
        logger.warning("已启用智能体只读诊断目录；日志和源码检索仅能访问管理员命名的根目录，每次读取或搜索仍需确认")
    elif config_gpt.gpt_agent_read_roots:
        logger.warning("已配置 gpt_agent_read_roots，但未找到有效的命名目录")
    workspace_sandbox = None
    workspace_web_renderer = None
    if config_gpt.gpt_agent_workspace:
        agent_workspace = AgentWorkspace(config_gpt.gpt_agent_workspace)
        if config_gpt.gpt_agent_workspace_web_render_enabled:
            workspace_web_renderer = WorkspaceWebRenderer(agent_workspace)
            logger.warning("已启用智能体工作区静态网页截图；脚本、嵌入页面和远程资源会被拒绝")
        if config_gpt.gpt_agent_workspace_execution_backend != "disabled":
            try:
                workspace_sandbox = WorkspaceSandbox(
                    agent_workspace,
                    backend=config_gpt.gpt_agent_workspace_execution_backend,
                    image=config_gpt.gpt_agent_workspace_execution_image,
                    timeout_seconds=config_gpt.gpt_agent_workspace_execution_timeout,
                    memory_mb=config_gpt.gpt_agent_workspace_execution_memory_mb,
                )
                backend = config_gpt.gpt_agent_workspace_execution_backend
                logger.warning(f"已启用智能体工作区脚本执行后端：{backend}；是否逐次确认由 gpt_agent_approval_mode 决定")
            except SandboxError as error:
                logger.warning(f"智能体工作区脚本执行未启用：{error}")
    elif (
        config_gpt.gpt_agent_workspace_web_render_enabled
        or config_gpt.gpt_agent_workspace_execution_backend != "disabled"
    ):
        logger.warning("已配置智能体工作区渲染或执行能力，但 gpt_agent_workspace 为空，相关工具不会注册")
    agent_runtime_options = {
        "confirmation_ttl_seconds": config_gpt.gpt_agent_confirm_timeout,
        "approval_mode": config_gpt.gpt_agent_approval_mode,
        "command_prefix": f"{preferred_address_prefix(getattr(config_nb, 'nickname', []))} 智能体".strip(),
        "session_approval_ttl_seconds": config_gpt.gpt_agent_session_approval_timeout,
        "plan_ttl_seconds": config_gpt.gpt_agent_plan_timeout,
        "max_steps": config_gpt.gpt_agent_max_steps,
        "max_model_turns": config_gpt.gpt_agent_max_model_turns,
        "task_timeout_seconds": config_gpt.gpt_agent_task_timeout,
        "model": config_gpt.gpt_agent_model,
        "error_message": config_gpt.gpt_error_message,
        "rate_limit_message": config_gpt.gpt_rate_limit_message,
        "workspace": config_gpt.gpt_agent_workspace,
        "workspace_sandbox": workspace_sandbox,
        "workspace_web_renderer": workspace_web_renderer,
        "managed_services": managed_services,
        "command_runner": command_runner,
        "command_skills": command_skills,
        "filesystem_scanner": filesystem_scanner,
        "readonly_sources": readonly_sources,
        "agent_turn": chat_runtime.agent_turn,
        "final_renderer": render_agent_final,
        "schedule_reminder": schedule_agent_reminder if config_gpt.gpt_agent_schedule_enabled else None,
        "schedule_target_reminder": schedule_target_agent_reminder if config_gpt.gpt_agent_schedule_enabled else None,
        "reminder_operation": operate_agent_reminder if config_gpt.gpt_agent_schedule_enabled else None,
    }
    if config_gpt.gpt_agent_enabled:
        logger.warning(f"智能体审批模式：{config_gpt.gpt_agent_approval_mode}")
    agent_runtime = create_agent_runtime(
        chat_service,
        **agent_runtime_options,
        access=AgentAccess.SUPERUSER,
    )
    member_agent_runtime = create_agent_runtime(
        chat_service,
        **agent_runtime_options,
        access=AgentAccess.MEMBER,
    )
    auto_persona = AutoPersonaInitializer(
        chat_runtime,
        group_enabled=config_gpt.gpt_auto_init_group,
        friend_enabled=config_gpt.gpt_auto_init_friend,
        group_persona_name=config_gpt.gpt_init_group_persona_name,
        friend_persona_name=config_gpt.gpt_init_friend_persona_name,
    )
    group_context_buffer = (
        GroupContextBuffer(
            max_entries_per_scope=max(64, config_gpt.gpt_group_context_max_messages * 4),
            retention_seconds=max(3600, config_gpt.gpt_group_context_max_age_seconds * 2),
            store_images=config_gpt.gpt_group_context_include_images,
            max_cached_image_bytes=config_gpt.gpt_attachment_max_total_size * 2,
        )
        if config_gpt.gpt_group_context_enabled
        else None
    )
    if group_context_buffer is not None:
        logger.success(
            "已开启共享聊天最近语境：最多 {} 条、{} 秒、{} 字符，历史图片={}",
            config_gpt.gpt_group_context_max_messages,
            config_gpt.gpt_group_context_max_age_seconds,
            config_gpt.gpt_group_context_max_chars,
            config_gpt.gpt_group_context_include_images,
        )
    
    driver = get_driver()
    @driver.on_startup
    async def d():
        remote_ready = True
        if remote_core:
            logger.info("连接共享 ChatGPTWeb 核心中")
            try:
                await chatbot.start()
            except Exception as error:
                logger.warning(f"共享 ChatGPTWeb 核心暂不可达，后续请求会自动重试：{error}")
                remote_ready = False
        else:
            logger.info("登录GPT账号中")
            loop = asyncio.get_running_loop()
            chatbot._start_task = asyncio.create_task(chatbot.__start__(loop))
        if remote_ready:
            await ensure_default_persona(chatbot)
        if config_gpt.gpt_agent_enabled and config_gpt.gpt_agent_schedule_enabled:
            await agent_scheduler.start()

    @driver.on_shutdown
    async def close_chatbot():
        await agent_scheduler.close()
        if group_context_buffer is not None:
            group_context_buffer.clear()
        if remote_core:
            await chatbot.close()
        else:
            start_task = chatbot._start_task
            if start_task and not start_task.done():
                start_task.cancel()
                await asyncio.gather(start_task, return_exceptions=True)
            await chatbot.close()

    async def get_current_render_mode(event: Event) -> str:
        """优先使用当前适配器会话范围的输出偏好。"""
        mode, _overridden = await chat_runtime.get_render_mode(
            ConversationKey.from_event(event),
            config_gpt.gpt_render_mode,
        )
        return mode

    async def extract_group_context_images(
        selection: GroupContextSelection,
        current_files: list,
        *,
        image_upload_enabled: bool,
    ) -> dict[tuple[int, int], str]:
        """Use only attachment capacity left after the current user message."""
        if (
            not config_gpt.gpt_group_context_include_images
            or not image_upload_enabled
            or config_gpt.gpt_group_context_max_images <= 0
        ):
            return {}
        remaining_count = min(
            config_gpt.gpt_group_context_max_images,
            max(0, config_gpt.gpt_attachment_max_count - len(current_files)),
        )
        remaining_size = max(
            0,
            config_gpt.gpt_attachment_max_total_size
            - sum(len(item.content) for item in current_files),
        )
        if not remaining_count or not remaining_size:
            return {}
        attachment_names: dict[tuple[int, int], str] = {}
        uploaded = 0
        for order, entry in enumerate(selection.entries, start=1):
            for image in entry.images:
                if image.source is None or uploaded >= remaining_count or remaining_size <= 0:
                    continue
                extracted = await extract_upload_files(
                    UniMessage([image.source]),
                    proxy=config_gpt.gpt_proxy,
                    upload_images=True,
                    upload_files=False,
                    max_file_size=min(config_gpt.gpt_file_max_size, remaining_size),
                    max_total_size=remaining_size,
                    max_count=1,
                    allowed_local_roots=config_gpt.gpt_attachment_local_roots,
                    allow_private_urls=config_gpt.gpt_attachment_allow_private_urls,
                    allowed_hosts=config_gpt.gpt_attachment_allowed_hosts,
                    download_timeout=config_gpt.gpt_attachment_download_timeout,
                    max_redirects=config_gpt.gpt_attachment_max_redirects,
                )
                if not extracted:
                    continue
                file = extracted[0]
                suffix = Path(file.name).suffix.lower()
                if not suffix or len(suffix) > 10 or not suffix[1:].isalnum():
                    suffix = ".png"
                file.name = f"group-context-{order}-image-{image.index}{suffix}"
                current_files.append(file)
                attachment_names[(entry.sequence, image.index)] = file.name
                uploaded += 1
                remaining_size -= len(file.content)
        if any(entry.images for entry in selection.entries):
            logger.info(
                "共享聊天语境图片处理完成：记录 {} 条，成功附加 {} 张，剩余附件位 {}",
                len(selection.entries),
                uploaded,
                max(0, config_gpt.gpt_attachment_max_count - len(current_files)),
            )
        return attachment_names

    if group_context_buffer is not None:
        group_context_capture = on_message(priority=0, block=False)

        @group_context_capture.handle()
        async def capture_group_context(
            event: Event,
            original_message: OriginalUniMsg,
        ) -> None:
            if not _is_group_context(event):
                return
            message_text = extract_chat_message(
                original_message,
                self_id=str(getattr(event, "self_id", "")),
            )
            if is_registered_command_text(
                message_text,
                [*getattr(config_nb, "nickname", []), *config_gpt.gpt_chat_start],
            ):
                return
            group_context_buffer.capture(event, original_message)

    chat = on_message(priority=config_gpt.gpt_chat_priority,rule=gpt_rule)
    @chat.handle()
    async def chat_handle(
        event: Event,
        matcher: Matcher,
        original_message: OriginalUniMsg,
    ):
        if _is_reply_event(event) and not config_gpt.gpt_replay_to_replay:
            await matcher.finish()
        group_context_selection = (
            group_context_buffer.select_before(
                event,
                original_message,
                max_messages=config_gpt.gpt_group_context_max_messages,
                max_age_seconds=config_gpt.gpt_group_context_max_age_seconds,
                max_chars=config_gpt.gpt_group_context_max_chars,
            )
            if group_context_buffer is not None and _is_group_context(event)
            else None
        )
        if group_context_buffer is not None and group_context_selection is not None:
            group_context_buffer.begin_chat(group_context_selection)
        key = ConversationKey.from_event(event)
        creator = ConversationCreator.from_event(event)
        model, prefer_paid_account = await select_model(event)
        image_upload_enabled = config_gpt.gpt_free_image or prefer_paid_account
        requested_images, requested_files = attachment_segment_counts(original_message)
        files = []
        if image_upload_enabled or config_gpt.gpt_file_upload:
            files = await extract_upload_files(
                original_message,
                proxy=config_gpt.gpt_proxy,
                upload_images=image_upload_enabled,
                upload_files=config_gpt.gpt_file_upload,
                max_file_size=config_gpt.gpt_file_max_size,
                max_total_size=config_gpt.gpt_attachment_max_total_size,
                max_count=config_gpt.gpt_attachment_max_count,
                allowed_local_roots=config_gpt.gpt_attachment_local_roots,
                allow_private_urls=config_gpt.gpt_attachment_allow_private_urls,
                allowed_hosts=config_gpt.gpt_attachment_allowed_hosts,
                download_timeout=config_gpt.gpt_attachment_download_timeout,
                max_redirects=config_gpt.gpt_attachment_max_redirects,
            )
        if requested_images or requested_files:
            extracted_images = sum(
                1
                for file in files
                if (
                    file.content_type == "image_asset_pointer"
                    or str(file.mime_type or "").lower().startswith("image/")
                )
            )
            logger.info(
                "聊天附件提取完成：请求图片 {}、其他文件 {}，成功 {}"
                "（图片 {}、其他文件 {}）",
                requested_images,
                requested_files,
                len(files),
                extracted_images,
                len(files) - extracted_images,
            )
        if (requested_images or requested_files) and not files:
            logger.warning(
                "本条聊天包含附件，但没有附件可传给核心："
                "gpt_free_image={}, paid_preferred={}, gpt_file_upload={}",
                config_gpt.gpt_free_image,
                prefer_paid_account,
                config_gpt.gpt_file_upload,
            )
            if group_context_buffer is not None and group_context_selection is not None:
                group_context_buffer.mark_consumed(group_context_selection)
            await finish_message(
                matcher,
                event,
                UniMessage.text(config_gpt.gpt_attachment_unavailable_message),
            )
            return
        message_text = extract_chat_message(
            original_message,
            self_id=str(getattr(event, "self_id", "")),
            image_upload_enabled=image_upload_enabled,
            file_upload_enabled=config_gpt.gpt_file_upload,
            uploaded_files=files,
        )
        if is_registered_command_text(
            message_text,
            [*getattr(config_nb, "nickname", []), *config_gpt.gpt_chat_start],
        ):
            logger.debug("已跳过被 Alconna 命令接管的普通聊天消息")
            if group_context_buffer is not None and group_context_selection is not None:
                group_context_buffer.mark_consumed(group_context_selection)
            await matcher.finish()
        prompt = build_chat_prompt(
            message_text,
            original_text=message_text,
            nicknames=[str(name) for name in getattr(config_nb, "nickname", [])],
            chat_prefixes=config_gpt.gpt_chat_start,
            include_prefix=config_gpt.gpt_chat_start_in_msg,
            empty_trigger_prompt=config_gpt.gpt_empty_trigger_prompt,
            direct_address_context_enabled=config_gpt.gpt_direct_address_context_enabled,
            direct_address_context_prompt=config_gpt.gpt_direct_address_context_prompt,
        )
        if (
            config_gpt.gpt_group_chat or config_gpt.gpt_group_context_enabled
        ) and _is_group_context(event):
            context_speakers = [
                {
                    "id": entry.speaker_id,
                    "name": entry.speaker_name or None,
                }
                for entry in (
                    group_context_selection.entries
                    if group_context_selection is not None
                    else ()
                )
            ]
            logger.debug(
                "群聊回复对象：id={}，name={}；近期语境发言者={}（不记录消息正文）",
                resolve_participant_identity(event),
                resolve_participant_display_name(event) or None,
                context_speakers,
            )
            prompt = format_group_speaker_prompt(event, prompt)
        if group_context_selection is not None and group_context_selection.entries:
            attachment_names = await extract_group_context_images(
                group_context_selection,
                files,
                image_upload_enabled=image_upload_enabled,
            )
            prompt = prepend_recent_group_context(
                prompt,
                format_recent_group_context(
                    group_context_selection.entries,
                    attachment_names=attachment_names,
                    max_chars=config_gpt.gpt_group_context_max_chars,
                ),
            )
        auto_result = await auto_persona.ensure_initialized(
            key,
            is_shared=_is_group_context(event),
            model=model,
            prefer_paid_account=prefer_paid_account,
            creator=creator,
        )
        if auto_result is not None and not auto_result.ok:
            logger.warning("当前会话的自动人设初始化失败：{}，将继续使用普通聊天", auto_result.text)
        try:
            reply = await chat_reply(
                chat_runtime,
                key,
                prompt,
                model=model,
                prefer_paid_account=prefer_paid_account,
                files=files,
                supports_markdown=supports_native_markdown(event),
                render_mode=await get_current_render_mode(event),
                render_markdown=chat_markdown_renderer,
                error_message=config_gpt.gpt_error_message,
                conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
                session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
                rate_limit_message=config_gpt.gpt_rate_limit_message,
                image_generation_failure_message=config_gpt.gpt_image_generation_failure_message,
                file_failure_message=config_gpt.gpt_file_failure_message,
                failure_diagnostics=failure_diagnostics,
                creator=creator,
            )
        except BaseException:
            if group_context_buffer is not None and group_context_selection is not None:
                group_context_buffer.cancel_chat(group_context_selection)
            raise
        if group_context_buffer is not None and group_context_selection is not None:
            after_send = lambda: group_context_buffer.mark_replied(group_context_selection)
        else:
            after_send = None
        await finish_message(matcher, event, reply, after_send=after_send)

    help_command = legacy_command(
        "gpt_help",
        aliases={"GPT帮助", "gpt帮助", "帮助GPT", "聊天帮助"},
        rule=gpt_operator_command_rule,
        priority=config_gpt.gpt_command_priority,
        block=True,
    )
    @help_command.handle()
    async def help_handle(event: Event, argument: Match[str], matcher: Matcher):
        topic = _argument_text(argument)
        await _finish_management_image(
            matcher,
            event,
            html=build_help_html(topic),
            fallback=format_help(topic),
        )

    render_mode_command = legacy_command(
        "输出模式",
        aliases={"富文本模式", "渲染模式"},
        rule=gpt_operator_command_rule,
        priority=config_gpt.gpt_command_priority,
        block=True,
    )
    @render_mode_command.handle()
    async def render_mode_handle(event: Event, argument: Match[str], matcher: Matcher):
        key = ConversationKey.from_event(event)
        raw_mode = _argument_text(argument).strip().lower()
        aliases = {
            "自动": "auto",
            "auto": "auto",
            "文本": "text",
            "纯文本": "text",
            "text": "text",
            "图片": "image",
            "图像": "image",
            "image": "image",
        }
        labels = {"auto": "自动", "text": "文本", "image": "图片"}
        if not raw_mode:
            mode, overridden = await chat_runtime.get_render_mode(key, config_gpt.gpt_render_mode)
            source = "当前会话" if overridden else "全局默认"
            await matcher.finish(f"当前富文本输出：{labels[mode]}（{source}）。\n可发送：输出模式 自动、文本、图片、默认。")
        if raw_mode in {"默认", "全局", "default"}:
            await chat_runtime.set_render_mode(key, None)
            await matcher.finish(f"已恢复全局默认输出策略：{labels[config_gpt.gpt_render_mode]}。")
        mode = aliases.get(raw_mode)
        if mode is None:
            await matcher.finish("可用输出模式：自动、文本、图片、默认。")
        await chat_runtime.set_render_mode(key, mode)
        await matcher.finish(f"已将当前会话的富文本输出切换为：{labels[mode]}。")

                        
    reset = legacy_command("reset",aliases={"重置记忆","重置","重置对话"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @reset.handle()
    async def reset_handle(event: Event, matcher: Matcher):
        reset_task = asyncio.create_task(restart_persona_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            supports_markdown=supports_native_markdown(event),
            render_mode=await get_current_render_mode(event),
            render_markdown=chat_markdown_renderer,
            error_message=config_gpt.gpt_error_message,
            conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
            session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
            rate_limit_message=config_gpt.gpt_rate_limit_message,
            failure_diagnostics=failure_diagnostics,
            creator=ConversationCreator.from_event(event),
        ))
        try:
            reply = await asyncio.wait_for(asyncio.shield(reset_task), timeout=12)
        except TimeoutError:
            await UniMessage.text("正在回到本次会话的人设开场，请稍候。").send(event)
            reply = await reset_task
        await finish_message(matcher, event, reply)

    new_conversation = legacy_command(
        "new_conversation",
        aliases={"另开对话", "开新篇"},
        rule=gpt_operator_command_rule,
        priority=config_gpt.gpt_command_priority,
        block=True,
    )
    @new_conversation.handle()
    async def new_conversation_handle(event: Event, matcher: Matcher):
        await finish_message(matcher, event, await new_conversation_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            supports_markdown=supports_native_markdown(event),
            render_mode=await get_current_render_mode(event),
            render_markdown=chat_markdown_renderer,
            error_message=config_gpt.gpt_error_message,
            conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
            session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
            rate_limit_message=config_gpt.gpt_rate_limit_message,
            failure_diagnostics=failure_diagnostics,
            creator=ConversationCreator.from_event(event),
        ))

    continue_previous_chapter = legacy_command(
        "continue_previous_chapter",
        aliases={"续写前篇", "整理前情"},
        rule=gpt_operator_command_rule,
        priority=config_gpt.gpt_command_priority,
        block=True,
    )
    @continue_previous_chapter.handle()
    async def continue_previous_chapter_handle(event: Event, matcher: Matcher):
        await finish_message(matcher, event, await continue_previous_chapter_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            supports_markdown=supports_native_markdown(event),
            render_mode=await get_current_render_mode(event),
            render_markdown=chat_markdown_renderer,
            error_message=config_gpt.gpt_error_message,
            conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
            session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
            rate_limit_message=config_gpt.gpt_rate_limit_message,
            failure_diagnostics=failure_diagnostics,
        ))

    context_status = legacy_command(
        "context_status",
        aliases={"上下文状态"},
        rule=gpt_operator_command_rule,
        priority=config_gpt.gpt_command_priority,
        block=True,
    )
    @context_status.handle()
    async def context_status_handle(event: Event, matcher: Matcher):
        await finish_message(
            matcher,
            event,
            await context_status_reply(chat_runtime, ConversationKey.from_event(event)),
        )

            
    last = legacy_command("backlast",aliases={"重置上一句","重置上句"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @last.handle()
    async def last_handle(event: Event, matcher: Matcher):
        await finish_message(matcher, event, await rewind_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            "-1",
            supports_markdown=supports_native_markdown(event),
            render_mode=await get_current_render_mode(event),
            render_markdown=chat_markdown_renderer,
            error_message=config_gpt.gpt_error_message,
            conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
            session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
            rate_limit_message=config_gpt.gpt_rate_limit_message,
            failure_diagnostics=failure_diagnostics,
        ))
            
            
    back = legacy_command("backloop",aliases={"回到过去"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @back.handle()
    async def back_handle(event: Event,argument: Match[str], matcher: Matcher):
        reference = _argument_text(argument)
        await finish_message(matcher, event, await rewind_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            reference,
            supports_markdown=supports_native_markdown(event),
            render_mode=await get_current_render_mode(event),
            render_markdown=chat_markdown_renderer,
            error_message=config_gpt.gpt_error_message,
            conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
            session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
            rate_limit_message=config_gpt.gpt_rate_limit_message,
            failure_diagnostics=failure_diagnostics,
        ))
            

    init = legacy_command("init",aliases={"初始化","初始化人格","加载人格","加载预设"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @init.handle()
    async def init_handle(event: Event,argument: Match[str], matcher: Matcher):
        await initialize_persona_handle(event, argument, matcher)
        
    plus_init = legacy_command("plus_init",aliases={"plus初始化","plus初始化人格","plus加载人格","plus加载预设"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @plus_init.handle()
    async def plus_init_handle(event: Event,argument: Match[str], matcher: Matcher):
        await initialize_persona_handle(event, argument, matcher, prefer_paid_account=True)

    async def initialize_persona_handle(
        event: Event,
        argument: Match[str],
        matcher: Matcher,
        prefer_paid_account: bool = False,
    ):
        raw_value = _argument_text(argument).strip()
        parts = raw_value.split(maxsplit=1)
        persona_name = parts[0] if parts else "默认"
        continue_existing = len(parts) > 1 and parts[1] == "继续"
        try:
            personalities = json.loads(personpath.read_text(encoding="utf-8"))
            persona = personalities[persona_name]
        except (OSError, json.JSONDecodeError, KeyError):
            await matcher.finish("未找到指定人设。")
        owner = str(persona.get("open", ""))
        if owner and owner != event.get_user_id():
            await matcher.finish("其他用户的私有人设不能使用。")
        if _is_group_context(event) and persona.get("r18"):
            if not _is_group_admin(event):
                await matcher.finish("群聊中仅群主或管理员可以初始化 R18 人设。")
        model, prefer_paid_account = await select_model(
            event,
            prefer_paid_account=prefer_paid_account,
        )
        await finish_message(matcher, event, await persona_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            persona_name,
            model=model,
            prefer_paid_account=prefer_paid_account,
            continue_existing=continue_existing,
            supports_markdown=supports_native_markdown(event),
            render_mode=await get_current_render_mode(event),
            render_markdown=chat_markdown_renderer,
            error_message=config_gpt.gpt_error_message,
            conversation_recovery_message=config_gpt.gpt_conversation_recovery_message,
            session_reauthentication_message=config_gpt.gpt_session_reauthentication_message,
            rate_limit_message=config_gpt.gpt_rate_limit_message,
            failure_diagnostics=failure_diagnostics,
            creator=ConversationCreator.from_event(event),
        ))

    personality_list = legacy_command("人设列表",aliases={"预设列表","人格列表"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @personality_list.handle()
    async def personality_list_handle(event: Event, matcher: Matcher):
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        text = list_personas(chatbot.personality, metadata).extract_plain_text()
        await _finish_management_table(
            matcher, event, title="人设列表", pages=persona_table_pages(chatbot.personality, metadata), fallback=text,
        )
                
            
    cat_personality = legacy_command("查看人设",aliases={"查看预设","查看人格"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @cat_personality.handle()
    async def cat_personality_handle(event: Event,argument: Match[str], matcher: Matcher):
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        name = _argument_text(argument)
        text = show_persona(chatbot.personality, metadata, name, event.get_user_id()).extract_plain_text()
        await _finish_management_document(
            matcher, event, title="人设详情", pages=markdown_pages_from_text("人设详情", text), fallback=text,
        )
                
                
    add_personality = legacy_command("添加人设",aliases={"添加预设","添加人格"},rule=gpt_persona_editor_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_personality.handle()
    async def add_personality_handle(event: Event,status: T_State,argument: Match[str], matcher: Matcher):
        status["creator_id"] = event.get_user_id()
        if _argument_text(argument).strip():
            await set_persona_name(status, _argument_text(argument), matcher)
        
    @add_personality.got("name",prompt="人设名叫什么？")
    async def add_personality_handle2(status: T_State, matcher: Matcher, name = Arg()):
        await set_persona_name(status, extract_text(name), matcher)
                
                
    @add_personality.got("r18",prompt="是R18人设吗？（回答 是 / 否)")
    async def add_personality_handle3(status: T_State, matcher: Matcher, r18 = Arg()):
        try:
            status["r18"] = parse_r18(extract_text(r18))
        except PersonaValidationError as error:
            await matcher.finish(str(error))

    @add_personality.got("open",prompt="要公开给其他人也可用吗？（回答 公开 / 私有)")
    async def add_personality_handle4(status: T_State, matcher: Matcher, open = Arg()):
        try:
            status["open"] = parse_visibility(
                extract_text(open),
                str(status["creator_id"]),
            )
        except PersonaValidationError as error:
            await matcher.finish(str(error))
            
    @add_personality.got("value",prompt="请发送人设内容")
    async def add_personality_handle5(event: Event, status: T_State, matcher: Matcher, value = Arg()):
        banned_words = ban_str_path.read_text(encoding="utf-8").splitlines()
        try:
            content = validate_value(extract_text(value), banned_words)
        except PersonaValidationError as error:
            await matcher.finish(str(error))
        personality = {
            "name": status["name"],
            "r18": status["r18"],
            "open": status["open"],
            "value": content,
        }
        await chatbot.add_personality(personality)
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        metadata[personality["name"]] = {
            "r18": personality["r18"],
            "open": personality["open"],
        }
        personpath.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        text = list_personas(chatbot.personality, metadata).extract_plain_text()
        await _finish_management_table(
            matcher, event, title="人设列表", pages=persona_table_pages(chatbot.personality, metadata), fallback=text,
        )
        
    async def set_persona_name(status: T_State, value: str, matcher: Matcher):
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        banned_words = ban_str_path.read_text(encoding="utf-8").splitlines()
        try:
            status["name"] = validate_name(value, metadata, banned_words)
        except PersonaValidationError as error:
            await matcher.finish(str(error))

    del_personality = legacy_command("删除人设",aliases={"删除人格","删除人设"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_personality.handle()
    async def del_personality_handle(event: Event,argument: Match[str], matcher: Matcher):
        name = _argument_text(argument).strip()
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        if not name or name not in metadata:
            await matcher.finish("没有找到指定人设。")
        await chatbot.del_personality(name)
        del metadata[name]
        personpath.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        text = list_personas(chatbot.personality, metadata).extract_plain_text()
        await _finish_management_table(
            matcher, event, title="人设列表", pages=persona_table_pages(chatbot.personality, metadata), fallback=text,
        )

    chat_history = legacy_command("history",aliases={"历史聊天","历史记录"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_history.handle()
    async def chat_history_handle(event: Event,argument: Match[str], matcher: Matcher):
        value, reverse_order = parse_history_view_argument(_argument_text(argument))
        history = await chat_runtime.get_visible_history(ConversationKey.from_event(event))
        fallback = format_history(
            history.entries,
            value,
            anonymize=config_gpt.gpt_history_anonymize,
            reverse_order=reverse_order,
            show_identity=config_gpt.gpt_history_show_identity,
            show_timestamp=config_gpt.gpt_history_show_timestamp,
            show_message_id=config_gpt.gpt_history_show_message_id,
        )
        await _finish_history_document(
            matcher,
            event,
            pages=build_history_pages(
                history.entries,
                value,
                anonymize=config_gpt.gpt_history_anonymize,
                reverse_order=reverse_order,
                show_identity=config_gpt.gpt_history_show_identity,
                show_timestamp=config_gpt.gpt_history_show_timestamp,
                show_message_id=config_gpt.gpt_history_show_message_id,
                font_scale=config_gpt.gpt_image_font_scale,
            ),
            fallback=fallback,
        )

    chat_conversations = legacy_command("conversations",aliases={"历史人设","历史会话"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_conversations.handle()
    async def chat_conversations_handle(event: Event, matcher: Matcher):
        key = ConversationKey.from_event(event)
        active = await chat_runtime.get_active_session(key)
        sessions = await chat_runtime.list_sessions(key)
        text = await list_sessions(chat_runtime, key)
        await _finish_management_table(
            matcher, event, title="历史会话", pages=session_table_pages(sessions, active.logical_id), fallback=text,
        )

    change_conversation = legacy_command("change_conversation",aliases={"切换会话"},rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @change_conversation.handle()
    async def change_conversation_handle(event: Event,argument: Match[str], matcher: Matcher):
        value = _argument_text(argument)
        await matcher.finish(await switch_session(chat_runtime, ConversationKey.from_event(event), value))

    status = legacy_command("gpt_status",aliases={"工作状态"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @status.handle()
    async def status_handle(event: Event, matcher: Matcher):
        failure_summary = failure_diagnostics.format()
        account_status = await chat_service.get_account_status()
        await _finish_management_image(
            matcher,
            event,
            html=build_account_status_html(account_status, failure_summary=failure_summary),
            fallback=format_account_status(account_status, failure_summary=failure_summary),
        )

    agent = legacy_command("agent", aliases={"智能体"}, rule=gpt_agent_rule, priority=config_gpt.gpt_command_priority, block=True)
    @agent.handle()
    async def agent_handle(event: Event, argument: Match[str], original_message: OriginalUniMsg, matcher: Matcher):
        if not config_gpt.gpt_agent_enabled:
            await matcher.finish("智能体功能未启用。请在配置中设置 gpt_agent_enabled=true 后重启机器人。")
        is_superuser = event.get_user_id() in config_nb.superusers
        if not is_superuser and not config_gpt.gpt_agent_member_enabled:
            await matcher.finish("智能体当前仅向机器人管理员开放。")
        value = _argument_text(argument)
        if agent_safety_policy.refusal_for(value):
            await matcher.finish(config_gpt.gpt_agent_sensitive_task_message)
        key = ConversationKey.from_event(event)
        creator = ConversationCreator.from_event(event)
        model, prefer_paid_account = await select_model(event)
        auto_result = await auto_persona.ensure_initialized(
            key,
            is_shared=_is_group_context(event),
            model=model,
            prefer_paid_account=prefer_paid_account,
            creator=creator,
        )
        if auto_result is not None and not auto_result.ok:
            logger.warning("当前会话的智能体自动人设初始化失败：{}", auto_result.text)
        await chat_runtime.ensure_session_creator(key, creator)
        runtime = agent_runtime if is_superuser else member_agent_runtime
        mentioned_user_ids, mention_context = _agent_mention_context(
            original_message,
            self_id=str(getattr(event, "self_id", "")),
        )
        context_parts = []
        if config_gpt.gpt_group_chat and _is_group_context(event):
            context_parts.append(format_group_speaker_prompt(event, "").strip())
        if mention_context:
            context_parts.append(mention_context)
        result = await runtime.execute(
            value,
            operator_id=event.get_user_id(),
            scope_id=get_access_session_id(event),
            conversation_key=key,
            delivery_target=get_target(event).dump(),
            delivery_user_id=event.get_user_id(),
            mentioned_user_ids=mentioned_user_ids,
            agent_context="\n".join(context_parts),
        )
        message = result if isinstance(result, UniMessage) else UniMessage.text(str(result))
        await finish_message(matcher, event, message)

    create_cdk = legacy_command("生成cdk", rule=gpt_superuser_rule, priority=config_gpt.gpt_command_priority, block=True)
    @create_cdk.handle()
    async def create_cdk_handle(event: Event, argument: Match[str], matcher: Matcher):
        note = _argument_text(argument)
        code = await cdk_registry.create(
            note=note,
            creator_id=get_event_user_id(event) or "",
            creator_scope=get_access_session_id(event),
        )
        source = note.strip() or "未备注"
        redeem_command = _redeem_command(code)
        await matcher.finish(
            f"已生成 CDK：{code}\n来源：{source}\n"
            "请复制以下命令并在目标会话发送：\n"
            f"{redeem_command}"
        )

    create_personal_cdk = legacy_command("生成个人cdk", aliases={"生成个人CDK"}, rule=gpt_superuser_rule, priority=config_gpt.gpt_command_priority, block=True)
    @create_personal_cdk.handle()
    async def create_personal_cdk_handle(event: Event, argument: Match[str], matcher: Matcher):
        note = _argument_text(argument)
        code = await cdk_registry.create(
            note=note,
            creator_id=get_event_user_id(event) or "",
            creator_scope=get_access_session_id(event),
            grant_kind="participant",
        )
        source = note.strip() or "未备注"
        redeem_command = _redeem_command(code)
        await matcher.finish(
            f"已生成个人 CDK：{code}\n来源：{source}\n"
            "请由目标用户复制以下命令，并在任意同平台私聊、群聊或频道发送：\n"
            f"{redeem_command}"
        )

    redeem_cdk = legacy_command("兑换", aliases={"出现吧"}, rule=gpt_cdk_redeem_rule, priority=config_gpt.gpt_command_priority, block=True)
    @redeem_cdk.handle()
    async def redeem_cdk_handle(event: Event, argument: Match[str], matcher: Matcher):
        await matcher.finish(await cdk_registry.redeem(
            _argument_text(argument),
            redeemer_id=get_event_user_id(event) or "",
            scope_id=get_access_session_id(event),
            grant_scope=add_white,
            participant_id=get_event_user_identity(event),
            grant_participant=add_personal_white,
        ))

    list_cdk = legacy_command("cdk列表", rule=gpt_superuser_rule, priority=config_gpt.gpt_command_priority, block=True)
    @list_cdk.handle()
    async def list_cdk_handle(event: Event, matcher: Matcher):
        text = f"{cdk_registry.format_list()}\n{cdk_registry.migration_summary()}"
        await _finish_management_table(
            matcher, event, title="CDK 列表", pages=cdk_table_pages(cdk_registry.list_records()), fallback=text,
        )

    revoke_cdk = legacy_command("作废cdk", rule=gpt_superuser_rule, priority=config_gpt.gpt_command_priority, block=True)
    @revoke_cdk.handle()
    async def revoke_cdk_handle(event: Event, argument: Match[str], matcher: Matcher):
        await matcher.finish(await cdk_registry.revoke(
            _argument_text(argument),
            operator_id=get_event_user_id(event) or "",
        ))

    leave_cdk = legacy_command("退出白名单", aliases={"结束吧"}, rule=gpt_command_rule, priority=config_gpt.gpt_command_priority, block=True)
    @leave_cdk.handle()
    async def leave_cdk_handle(event: Event, matcher: Matcher):
        await matcher.finish(await del_white(get_access_session_id(event)))

    leave_personal_cdk = legacy_command("退出个人白名单", aliases={"退出个人授权"}, rule=gpt_cdk_redeem_rule, priority=config_gpt.gpt_command_priority, block=True)
    @leave_personal_cdk.handle()
    async def leave_personal_cdk_handle(event: Event, matcher: Matcher):
        await matcher.finish(await del_personal_white(get_event_user_identity(event)))
        
    ban_list = legacy_command("黑名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @ban_list.handle()
    async def ban_list_handle(event: Event,argument: Match[str], matcher: Matcher):
        target = _argument_text(argument).strip()
        bans = json.loads(banpath.read_text(encoding="utf-8"))
        text = format_bans(bans, target)
        await _finish_management_table(
            matcher, event, title="黑名单列表", pages=blacklist_table_pages(bans, target), fallback=text,
        )
        
    ban_del = legacy_command("解黑",rule=gpt_manage_rule,aliases={"解除黑名单","删除黑名单"},priority=config_gpt.gpt_command_priority,block=True)
    @ban_del.handle()
    async def ban_del_handle(event: Event,argument: Match[str], matcher: Matcher):
        target = _argument_text(argument).strip()
        bans = json.loads(banpath.read_text(encoding="utf-8"))
        if not target or target not in bans:
            await matcher.finish("没有找到指定黑名单目标。")
        del bans[target]
        banpath.write_text(json.dumps(bans, ensure_ascii=False, indent=2), encoding="utf-8")
        await matcher.finish("已解除黑名单。")
        
    del_white_cmd = legacy_command("删除白名单",aliases={"解除白名单","解白"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_white_cmd.handle()
    async def del_white_handle(event: Event,argument: Match[str], matcher: Matcher):
        try:
            target, _ = parse_access_target(
                _argument_text(argument),
                default_target=get_access_session_id(event),
            )
        except ValueError as error:
            await matcher.finish(str(error))
        await matcher.finish(await del_white(target))
        
    white_list_cmd = legacy_command("白名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @white_list_cmd.handle()
    async def white_list_handle(event: Event, matcher: Matcher):
        whitelist = read_whitelist()
        paid = json.loads(plusstatus.read_text(encoding="utf-8"))
        text = format_whitelist(whitelist, paid)
        await _finish_management_table(
            matcher, event, title="白名单列表", pages=whitelist_table_pages(whitelist, paid), fallback=text,
        )
        
    md_status_cmd = legacy_command("md状态",rule=gpt_operator_command_rule,priority=config_gpt.gpt_command_priority,block=True)
    @md_status_cmd.handle()
    async def md_status_cmd_handle(matcher: Matcher):
        await matcher.finish("当前版本会按消息内容与适配器能力自动选择文本或图片渲染，md状态不再需要单独设置。")
        
    add_plus_cmd = legacy_command("添加plus",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_plus_cmd.handle()
    async def add_plus_handle(argument: Match[str], matcher: Matcher):
        settings = json.loads(plusstatus.read_text(encoding="utf-8"))
        try:
            message = grant_paid_access(
                settings,
                _argument_text(argument),
            )
        except ValueError as error:
            await matcher.finish(str(error))
        plusstatus.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await matcher.finish(message)
    
    del_plus_cmd = legacy_command("删除plus",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_plus_cmd.handle()
    async def del_plus_handle(argument: Match[str], matcher: Matcher):
        settings = json.loads(plusstatus.read_text(encoding="utf-8"))
        try:
            message = revoke_paid_access(
                settings,
                _argument_text(argument),
            )
        except ValueError as error:
            await matcher.finish(str(error))
        plusstatus.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await matcher.finish(message)
    
    plus_change_cmd = legacy_command("plus切换",rule=plus_status,priority=config_gpt.gpt_command_priority,block=True)
    @plus_change_cmd.handle()
    async def plus_change_handle(event: Event, argument: Match[str], matcher: Matcher):
        model = resolve_paid_model(_argument_text(argument))
        if not model:
            await matcher.finish("未识别模型，请输入已配置的模型别名或完整模型名。")
        settings = json.loads(plusstatus.read_text(encoding="utf-8"))
        if not settings.get("status", True):
            await matcher.finish("管理员已关闭全局 Plus 使用。")
        identifier = get_access_session_id(event)
        settings[identifier] = model
        plusstatus.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await chat_runtime.set_model_preference(
            ConversationKey.from_event(event),
            model,
            prefer_paid_account=True,
        )
        await matcher.finish(f"已将当前逻辑会话切换为 {model}。")
    
    plus_all_status_cmd = legacy_command("全局plus",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @plus_all_status_cmd.handle()
    async def plus_all_status_handle(argument: Match[str], matcher: Matcher):
        settings = json.loads(plusstatus.read_text(encoding="utf-8"))
        try:
            message = set_global_paid_enabled(
                settings,
                _argument_text(argument),
            )
        except ValueError as error:
            await matcher.finish(str(error))
        plusstatus.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await matcher.finish(message)
    
    
    
    add_white_cmd = legacy_command("添加白名单",aliases={"加白"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_white_cmd.handle()
    async def add_white_handle(event: Event, argument: Match[str], matcher: Matcher):
        try:
            target, paid = parse_access_target(
                _argument_text(argument),
                default_target=get_access_session_id(event),
            )
        except ValueError as error:
            await matcher.finish(str(error))
        await matcher.finish(await add_white(target, paid))

    session_id_cmd = legacy_command("session_id", aliases={"会话标识"}, rule=gpt_manage_rule, priority=config_gpt.gpt_command_priority, block=True)
    @session_id_cmd.handle()
    async def session_id_handle(event: Event, matcher: Matcher):
        await matcher.finish(f"当前访问范围标识：{get_access_session_id(event)}")

else:
    logger.warning("未检测到gpt账号信息，插件未成功加载")
