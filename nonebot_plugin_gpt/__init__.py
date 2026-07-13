from ChatGPTWeb import ChatService, chatgpt
from ChatGPTWeb.config import Personality
from nonebot.log import logger
from nonebot import on_message
from nonebot.matcher import Matcher
from nonebot.params import Arg, EventMessage
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot import get_driver
from nonebot_plugin_alconna import Match, on_alconna
from importlib.metadata import version
import asyncio
import json


from .config import config_gpt,Config
from .source import ban_str_path, banpath, conversation_store_path, data_dir, personpath, plusstatus, whitepath
from .agent_runtime import create_agent_runtime
from .check import add_white, del_white, get_access_session_id, gpt_command_rule, gpt_manage_rule, gpt_rule, gpt_superuser_rule, plus_status, read_whitelist
from .command_compat import build_legacy_command
from .chat_runtime import ChatRuntime
from .context_policy import ContextPolicy
from .conversation import ConversationKey, ConversationStore
from .runtime_handlers import chat_reply, persona_reply, restart_persona_reply, rewind_reply
from .session_commands import list_sessions, switch_session
from .model_selection import resolve_paid_model, select_model
from .attachments import extract_image_files
from .persona_views import list_personas, show_persona
from .persona_editor import (
    PersonaValidationError,
    extract_text,
    parse_r18,
    parse_visibility,
    validate_name,
    validate_value,
)
from .history_views import format_history, format_history_tree
from .management_views import format_account_status
from .access_views import format_bans, format_whitelist, parse_access_target
from .plus_views import grant_paid_access, revoke_paid_access, set_global_paid_enabled
from .personality_service import ensure_default_persona
from .event_scope import resolve_event_scope


def legacy_command(name, aliases=None, rule=None, priority=1, block=False):
    """用 Alconna 解析旧指令，保持原有名称、别名和规则不变。"""
    if rule is gpt_rule:
        rule = gpt_command_rule
    return on_alconna(
        build_legacy_command(name, aliases),
        rule=rule,
        use_cmd_start=True,
        use_cmd_sep=True,
        priority=priority,
        block=block,
    )


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


try:
    __version__ = version("nonebot_plugin_gpt")
except Exception:
    __version__ = None
    
    

__plugin_meta__ = PluginMetadata(
    name="ChatGPT 聊天",
    description="通过浏览器使用 ChatGPT，基于 Alconna 与 UniMessage 提供跨平台聊天能力",
    usage="""
聊天：@机器人或配置的前缀后发送内容。
会话：初始化、人设列表、历史聊天、历史会话、切换会话、重置、回到过去。
管理：工作状态、黑名单列表、解黑、白名单列表、添加白名单、删除白名单、会话标识。
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

if isinstance(config_gpt.gpt_session,list):
    personality = Personality([],data_dir)
    
    chatbot = chatgpt(
        sessions = config_gpt.gpt_session,
        plugin = True,
        arkose_status = config_gpt.arkose_status,
        chat_file = data_dir,
        proxy = config_gpt.gpt_proxy,
        begin_sleep_time = config_gpt.begin_sleep_time,
        personality=personality,
        save_screen=config_gpt.gpt_save_screen,
        headless=config_gpt.gpt_headless,
        local_js=config_gpt.gpt_local_js,
        )
    chat_service = ChatService(chatbot)
    agent_runtime = create_agent_runtime(chat_service)
    chat_runtime = ChatRuntime(
        chat_service,
        ConversationStore(conversation_store_path),
        ContextPolicy(
            mode=config_gpt.gpt_context_compaction_mode,
            utilization_threshold=config_gpt.gpt_context_compaction_threshold,
            minimum_estimated_tokens=config_gpt.gpt_context_compaction_min_tokens,
        ),
    )
    
    driver = get_driver()
    @driver.on_startup
    async def d():
        logger.info("登录GPT账号中")
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(chatbot.__start__(loop),loop)
        await ensure_default_persona(chatbot)

    chat = on_message(priority=config_gpt.gpt_chat_priority,rule=gpt_rule)
    @chat.handle()
    async def chat_handle(event: Event, matcher: Matcher, text = EventMessage()):
        if _is_reply_event(event) and not config_gpt.gpt_replay_to_replay:
            await matcher.finish()
        prompt = text.extract_plain_text().strip()
        if not config_gpt.gpt_chat_start_in_msg:
            for chat_start in config_gpt.gpt_chat_start:
                if prompt.startswith(chat_start):
                    prompt = prompt[len(chat_start):].strip()
                    break
        if not prompt:
            await matcher.finish("请发送想聊天的内容。")
        if config_gpt.group_chat and _is_group_context(event):
            prompt = f"{event.get_user_id()}对你说：{prompt}"
        model, prefer_paid_account = await select_model(event)
        files = []
        if config_gpt.gpt_free_image or prefer_paid_account:
            files = await extract_image_files(text, proxy=config_gpt.gpt_proxy)
        await matcher.finish(await chat_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            prompt,
            model=model,
            prefer_paid_account=prefer_paid_account,
            files=files,
            render_mode=config_gpt.gpt_render_mode,
        ))

                        
    reset = legacy_command("reset",aliases={"重置记忆","重置","重置对话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @reset.handle()
    async def reset_handle(event: Event, matcher: Matcher):
        await matcher.finish(await restart_persona_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            render_mode=config_gpt.gpt_render_mode,
        ))
    
            
    last = legacy_command("backlast",aliases={"重置上一句","重置上句"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @last.handle()
    async def last_handle(event: Event, matcher: Matcher):
        await matcher.finish(await rewind_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            "-1",
            render_mode=config_gpt.gpt_render_mode,
        ))
            
            
    back = legacy_command("backloop",aliases={"回到过去"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @back.handle()
    async def back_handle(event: Event,argument: Match[str], matcher: Matcher):
        reference = argument.result if argument.available else ""
        await matcher.finish(await rewind_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            reference,
            render_mode=config_gpt.gpt_render_mode,
        ))
            

    init = legacy_command("init",aliases={"初始化","初始化人格","加载人格","加载预设"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @init.handle()
    async def init_handle(event: Event,argument: Match[str], matcher: Matcher):
        await initialize_persona_handle(event, argument, matcher)
        
    plus_init = legacy_command("plus_init",aliases={"plus初始化","plus初始化人格","plus加载人格","plus加载预设"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @plus_init.handle()
    async def plus_init_handle(event: Event,argument: Match[str], matcher: Matcher):
        await initialize_persona_handle(event, argument, matcher, prefer_paid_account=True)

    async def initialize_persona_handle(
        event: Event,
        argument: Match[str],
        matcher: Matcher,
        prefer_paid_account: bool = False,
    ):
        raw_value = argument.result.strip() if argument.available else ""
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
        await matcher.finish(await persona_reply(
            chat_runtime,
            ConversationKey.from_event(event),
            persona_name,
            model=model,
            prefer_paid_account=prefer_paid_account,
            continue_existing=continue_existing,
            render_mode=config_gpt.gpt_render_mode,
        ))

    personality_list = legacy_command("人设列表",aliases={"预设列表","人格列表"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @personality_list.handle()
    async def personality_list_handle(event: Event, matcher: Matcher):
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        await matcher.finish(list_personas(chatbot.personality, metadata))
                
            
    cat_personality = legacy_command("查看人设",aliases={"查看预设","查看人格"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @cat_personality.handle()
    async def cat_personality_handle(event: Event,argument: Match[str], matcher: Matcher):
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        name = argument.result if argument.available else ""
        await matcher.finish(show_persona(
            chatbot.personality,
            metadata,
            name,
            event.get_user_id(),
        ))
                
                
    add_personality = legacy_command("添加人设",aliases={"添加预设","添加人格"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_personality.handle()
    async def add_personality_handle(event: Event,status: T_State,argument: Match[str], matcher: Matcher):
        status["creator_id"] = event.get_user_id()
        if argument.available and argument.result.strip():
            await set_persona_name(status, argument.result, matcher)
        
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
    async def add_personality_handle5(status: T_State, matcher: Matcher, value = Arg()):
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
        await matcher.finish(list_personas(chatbot.personality, metadata))
        
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
        name = argument.result.strip() if argument.available else ""
        metadata = json.loads(personpath.read_text(encoding="utf-8"))
        if not name or name not in metadata:
            await matcher.finish("没有找到指定人设。")
        await chatbot.del_personality(name)
        del metadata[name]
        personpath.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        await matcher.finish(list_personas(chatbot.personality, metadata))

    chat_history = legacy_command("history",aliases={"历史聊天","历史记录"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_history.handle()
    async def chat_history_handle(event: Event,argument: Match[str], matcher: Matcher):
        value = argument.result if argument.available else ""
        history = await chat_runtime.get_history(ConversationKey.from_event(event))
        await matcher.finish(format_history(history, value))

    chat_history = legacy_command("history_tree",aliases={"历史聊天树","历史记录树"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_history.handle()
    async def chat_history_handle(event: Event, matcher: Matcher):
        key = ConversationKey.from_event(event)
        state = await chat_runtime.get_active_session(key)
        history = await chat_runtime.get_history(key)
        await matcher.finish(format_history_tree(state, len(history)))

    chat_conversations = legacy_command("conversations",aliases={"历史人设","历史会话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_conversations.handle()
    async def chat_conversations_handle(event: Event, matcher: Matcher):
        await matcher.finish(await list_sessions(chat_runtime, ConversationKey.from_event(event)))

    change_conversation = legacy_command("change_conversation",aliases={"切换会话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @change_conversation.handle()
    async def change_conversation_handle(event: Event,argument: Match[str], matcher: Matcher):
        value = argument.result if argument.available else ""
        await matcher.finish(await switch_session(chat_runtime, ConversationKey.from_event(event), value))

    status = legacy_command("gpt_status",aliases={"工作状态"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @status.handle()
    async def status_handle(matcher: Matcher):
        await matcher.finish(format_account_status(await chat_service.get_account_status()))

    agent = legacy_command("agent", aliases={"智能体"}, rule=gpt_superuser_rule, priority=config_gpt.gpt_command_priority, block=True)
    @agent.handle()
    async def agent_handle(argument: Match[str], matcher: Matcher):
        if not config_gpt.gpt_agent_enabled:
            await matcher.finish("智能体功能未启用。请在配置中设置 gpt_agent_enabled=true 后重启机器人。")
        value = argument.result if argument.available else ""
        await matcher.finish(await agent_runtime.execute(value))
        
    ban_list = legacy_command("黑名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @ban_list.handle()
    async def ban_list_handle(event: Event,argument: Match[str], matcher: Matcher):
        target = argument.result.strip() if argument.available else ""
        bans = json.loads(banpath.read_text(encoding="utf-8"))
        await matcher.finish(format_bans(bans, target))
        
    ban_del = legacy_command("解黑",rule=gpt_manage_rule,aliases={"解除黑名单","删除黑名单"},priority=config_gpt.gpt_command_priority,block=True)
    @ban_del.handle()
    async def ban_del_handle(event: Event,argument: Match[str], matcher: Matcher):
        target = argument.result.strip() if argument.available else ""
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
                argument.result if argument.available else "",
                default_target=get_access_session_id(event),
            )
        except ValueError as error:
            await matcher.finish(str(error))
        await matcher.finish(await del_white(target))
        
    white_list_cmd = legacy_command("白名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @white_list_cmd.handle()
    async def white_list_handle(matcher: Matcher):
        whitelist = read_whitelist()
        paid = json.loads(plusstatus.read_text(encoding="utf-8"))
        await matcher.finish(format_whitelist(whitelist, paid))
        
    md_status_cmd = legacy_command("md状态",rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
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
                argument.result if argument.available else "",
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
                argument.result if argument.available else "",
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
        model = resolve_paid_model(argument.result if argument.available else "")
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
                argument.result if argument.available else "",
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
                argument.result if argument.available else "",
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
