from ChatGPTWeb import chatgpt
from ChatGPTWeb.config import Personality
from nonebot.log import logger
from nonebot import on_command,on_message,on_notice
from nonebot.adapters.onebot.v11 import Message,MessageEvent,GroupIncreaseNoticeEvent,FriendAddNoticeEvent,Bot
from nonebot.adapters.qq.event import MessageEvent as QQMessageEvent,GroupAddRobotEvent,FriendAddEvent,GuildMemberUpdateEvent
from nonebot.adapters.qq.message import Message as QQMessage
from nonebot.adapters.qq import Bot as QQBot
from nonebot.matcher import Matcher,current_bot
from nonebot.params import Arg, CommandArg,EventMessage
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot import get_driver
from importlib.metadata import version
import asyncio


from .config import config_gpt,Config
from .source import data_dir
from .check import gpt_manage_rule,gpt_rule,plus_status

from .api import (
    add_default_ps,
    chat_msg,
    reset_history,
    back_last,
    back_anywhere,
    init_gpt,
    ps_list,
    cat_ps,
    add_ps1,
    add_ps2,
    add_ps3,
    add_ps4,
    add_ps5,
    del_ps,
    chatmsg_history,
    status_pic,
    black_list,
    remove_ban_user,
    add_white_list,
    del_white_list,
    white_list,
    md_status,
    get_id_from_guild_group,
    random_cdk_api,
    add_checker_api,
    add_plus,
    del_plus,
    plus_change,
    plus_all_status,
    init_personal_api,
    chatmsg_history_tree,
    conversation_change,
    conversations_list
    
)

try:
    __version__ = version("nonebot_plugin_gpt")
except Exception:
    __version__ = None
    
    

__plugin_meta__ = PluginMetadata(
    name="ChatGPT 聊天",
    description="通过浏览器使用 ChatGPT,兼容 onebot v11 与 adapter-qq 适配器",
    usage="""
| 指令 | 适配器 | 权限 | 需要@ | 范围 |  说明 |
|:-----:|:----:|:----:|:----:|:----:|:----:|
| @bot 聊天内容... | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | @或者叫名+内容 开始聊天，随所有者白名单模式设置改变 |
| 初始化 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 初始化(人设名) |
| 重置 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 回到初始化人设后的第二句话时 |
| 重置上一句 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 刷新上一句的回答 |
| 回到过去 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 回到过去 <对话序号/p_id/最后一次出现的关键词> ，回到括号内的对话时间点|
| 人设列表 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看可用人设列表 |
| 查看人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看人设的具体内容 |
| 添加人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 添加人设 (人设名) |
| 历史聊天 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看当前人格历史聊天记录 |
| md状态开启 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 用户自开启markdown输出内容 |
| md状态关闭 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 用户自关闭markdown输出内容 |
| 删除人设 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除人设 (人设名) |
| 黑名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看黑名单列表 |
| 解黑 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 解黑<账号> ，解除黑名单 |
| 白名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看白名单列表 |
| 工作状态 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看当前所有账号的工作状态 |
| 添加plus | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 添加plus 群号/账号/QQ适配器openid |
| 删除plus | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除plus 群号/账号/QQ适配器openid |
| plus切换 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | plus切换 <模型名称> ，如 3.5/4/4o，白名单状态开启后，仅支持有plus状态的|
| 全局plus | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 全局plus 开启/关闭，关闭后所有人的plus状态不可用，仅能使用3.5模型，超管自己除外 |
| 删除白名单 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除白名单 <账号/群号> (个人/群) ，删除白名单，最后不写默认为群 |
| 添加白名单 | OneBot | 超级管理员/超管群 | 是 | 群聊/私聊 | 添加白名单(plus) <账号/群号> (个人/群) ，添加白名单，最后不写默认为群，加了plus字样则默认同时添加进plus状态 |
| 获取本地id | qq | 无/白名单 | 是 | 群聊/频道 | 群聊内获取id |
| 生成cdk | qq | 超管群 | 是 | 群聊/频道 | 生成cdk <群号/其他信息>，以绑定信息方式生成白名单cdk |
| 出现吧 | qq | 无 | 是 | 群聊/频道 | 出现吧 <cdk>，以绑定id形式使用cdk加入白名单 |
| 结束吧 | qq | 白名单 | 是 | 群聊/频道 | 结束吧 ，用户自主解除白名单 |
    """,
    type="application",
    config=Config,
    homepage="https://github.com/nek0us/nonebot-plugin-gpt",
    supported_adapters={"~onebot.v11","~qq"},
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
        httpx_status=config_gpt.gpt_httpx,
        save_screen=config_gpt.gpt_save_screen,
        headless=config_gpt.gpt_headless,
        local_js=config_gpt.gpt_local_js,
        )
    
    driver = get_driver()
    @driver.on_startup
    async def d():
        logger.info("登录GPT账号中")
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(chatbot.__start__(loop),loop)
        await add_default_ps(chatbot)

    chat = on_message(priority=config_gpt.gpt_chat_priority,rule=gpt_rule)
    @chat.handle()
    async def chat_handle(bot: Bot,event: MessageEvent|QQMessageEvent,text:Message|QQMessage = EventMessage()):
        await chat_msg(bot,event,chatbot,text)

                        
    reset = on_command("reset",aliases={"重置记忆","重置","重置对话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @reset.handle()
    async def reset_handle(event: MessageEvent|QQMessageEvent,text:Message|QQMessage = EventMessage()):
        await reset_history(event,chatbot,text)
    
            
    last = on_command("backlast",aliases={"重置上一句","重置上句"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @last.handle()
    async def last_handle(event: MessageEvent|QQMessageEvent,text:Message|QQMessage = EventMessage()):
        await back_last(event,chatbot,text)
            
            
    back = on_command("backloop",aliases={"回到过去"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @back.handle()
    async def back_handle(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage = CommandArg()):
        await back_anywhere(event,chatbot,arg)
            

    init = on_command("init",aliases={"初始化","初始化人格","加载人格","加载预设"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @init.handle()
    async def init_handle(event: MessageEvent|QQMessageEvent,arg :Message|QQMessage = CommandArg()):
        await init_gpt(event,chatbot,arg)
        
    plus_init = on_command("plus_init",aliases={"plus初始化","plus初始化人格","plus加载人格","plus加载预设"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @plus_init.handle()
    async def plus_init_handle(event: MessageEvent|QQMessageEvent,arg :Message|QQMessage = CommandArg()):
        await init_gpt(event,chatbot,arg,True)

    personality_list = on_command("人设列表",aliases={"预设列表","人格列表"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @personality_list.handle()
    async def personality_list_handle(event: MessageEvent|QQMessageEvent):
        await ps_list(event,chatbot)
                
            
    cat_personality = on_command("查看人设",aliases={"查看预设","查看人格"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @cat_personality.handle()
    async def cat_personality_handle(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage = CommandArg()):
        await cat_ps(event,chatbot,arg)
                
                
    add_personality = on_command("添加人设",aliases={"添加预设","添加人格"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_personality.handle()
    async def add_personality_handle(event: MessageEvent|QQMessageEvent,status: T_State,arg :Message|QQMessage = CommandArg()):
        await add_ps1(event,status,arg)
        
    @add_personality.got("name",prompt="人设名叫什么？")
    async def add_personality_handle2(status: T_State,name: Message|QQMessage = Arg()):
        await add_ps2(status,name)
                
                
    @add_personality.got("r18",prompt="是R18人设吗？（回答 是 / 否)")
    async def add_personality_handle3(status: T_State,r18: Message|QQMessage = Arg()):
        await add_ps3(status,r18)

    @add_personality.got("open",prompt="要公开给其他人也可用吗？（回答 公开 / 私有)")
    async def add_personality_handle4(status: T_State,open: Message|QQMessage = Arg()):
        await add_ps4(status,open)
            
    @add_personality.got("value",prompt="请发送人设内容")
    async def add_personality_handle5(status: T_State,value: Message|QQMessage = Arg()):
        await add_ps5(status,value,chatbot)
        
    del_personality = on_command("删除人设",aliases={"删除人格","删除人设"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_personality.handle()
    async def del_personality_handle(event: MessageEvent|QQMessageEvent,arg :Message|QQMessage = CommandArg()):
        await del_ps(event,chatbot,arg)

    chat_history = on_command("history",aliases={"历史聊天","历史记录"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_history.handle()
    async def chat_history_handle(bot:Bot,event: MessageEvent|QQMessageEvent,text:Message|QQMessage = CommandArg()):
        await chatmsg_history(bot,event,chatbot,text)

    chat_history = on_command("history_tree",aliases={"历史聊天树","历史记录树"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_history.handle()
    async def chat_history_handle(event: MessageEvent|QQMessageEvent,text:Message|QQMessage = CommandArg()):
        await chatmsg_history_tree(event,chatbot,text)

    chat_conversations = on_command("conversations",aliases={"历史人设","历史会话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_conversations.handle()
    async def chat_conversations_handle(event: MessageEvent|QQMessageEvent):
        await conversations_list(chatbot,event)

    change_conversation = on_command("change_conversation",aliases={"切换会话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @change_conversation.handle()
    async def change_conversation_handle(event: MessageEvent|QQMessageEvent,arg:Message|QQMessage = CommandArg()):
        await conversation_change(event,arg)

    status = on_command("gpt_status",aliases={"工作状态"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @status.handle()
    async def status_handle(matcher: Matcher):
        await status_pic(matcher,chatbot)
        
    ban_list = on_command("黑名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @ban_list.handle()
    async def ban_list_handle(event: MessageEvent|QQMessageEvent,arg :Message|QQMessage = CommandArg()):
        await black_list(chatbot,event,arg)
        
    ban_del = on_command("解黑",rule=gpt_manage_rule,aliases={"解除黑名单","删除黑名单"},priority=config_gpt.gpt_command_priority,block=True)
    @ban_del.handle()
    async def ban_del_handle(arg: Message|QQMessage = CommandArg()):
        await remove_ban_user(arg)
        
    del_white_cmd = on_command("删除白名单",aliases={"解除白名单","解白"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_white_cmd.handle()
    async def del_white_handle(arg: Message|QQMessage = CommandArg()):
        await del_white_list(arg)
        
    white_list_cmd = on_command("白名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @white_list_cmd.handle()
    async def white_list_handle():
        await white_list(chatbot)
        
    md_status_cmd = on_command("md状态",rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @md_status_cmd.handle()
    async def md_status_cmd_handle(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage = CommandArg()):
        await md_status(event,arg)
        
    add_plus_cmd = on_command("添加plus",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_plus_cmd.handle()
    async def add_plus_handle(arg: Message|QQMessage = CommandArg()):
        await add_plus(arg)
    
    del_plus_cmd = on_command("删除plus",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_plus_cmd.handle()
    async def del_plus_handle(arg: Message|QQMessage = CommandArg()):
        await del_plus(arg)
    
    plus_change_cmd = on_command("plus切换",rule=plus_status,priority=config_gpt.gpt_command_priority,block=True)
    @plus_change_cmd.handle()
    async def plus_change_handle(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage = CommandArg()):
        await plus_change(event,arg)
    
    plus_all_status_cmd = on_command("全局plus",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @plus_all_status_cmd.handle()
    async def plus_all_status_handle(arg: Message|QQMessage = CommandArg()):
        await plus_all_status(arg)
    
    
    
    # ------------------------------ adapter-OneBot        
    add_white_cmd = on_command("添加白名单",aliases={"加白"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_white_cmd.handle()
    async def add_white_handle(arg: Message = CommandArg()):
        await add_white_list(arg)
        
    # ------------------------------ adapter-qq
    get_local_id = on_command("获取本地id",rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @get_local_id.handle()
    async def get_local_id_handle(event: QQMessageEvent,matcher: Matcher):
        id,value = await get_id_from_guild_group(event)
        await matcher.finish(id)  
        
    random_cdk = on_command("生成cdk",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @random_cdk.handle()
    async def random_cdk_handle(arg:QQMessage = CommandArg()):
        await random_cdk_api(arg)
        
    add_checker = on_command("出现吧",priority=config_gpt.gpt_command_priority,block=True)
    @add_checker.handle()
    async def add_checker_handle(event: QQMessageEvent,arg: QQMessage = CommandArg()):
        await add_checker_api(event,arg)
    
    del_checker = on_command("结束吧",rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_checker.handle()
    async def del_checker_handle(event: QQMessageEvent):
        id,value = await get_id_from_guild_group(event)
        await del_white_list(id)
        
    init_personal = on_notice(block=False,priority=config_gpt.gpt_chat_priority)
    @init_personal.handle()
    async def init_personal_handle(event: GroupAddRobotEvent|FriendAddNoticeEvent|GroupIncreaseNoticeEvent|FriendAddEvent|GuildMemberUpdateEvent):
        if isinstance(event,GroupAddRobotEvent):
            # QQ群
            if config_gpt.gpt_auto_init_group:
                if not config_gpt.gpt_init_group_pernal_name:
                    logger.warning(f"检测到已开启入群初始化人设，但未配置具体人设名，类型 GroupAddRobotEvent, id: {event.group_openid} 入群初始化人设失败")
                else:
                    logger.info(f"检测到已开启入群初始化人设，类型 GroupAddRobotEvent, id: {event.group_openid} 即将入群初始化人设 {config_gpt.gpt_init_group_pernal_name}")
                    await init_personal_api(chatbot,id=event.group_openid,personal_name=config_gpt.gpt_init_group_pernal_name,type_from='QQgroup')
        elif isinstance(event,FriendAddNoticeEvent):
            # onebot 好友
            if config_gpt.gpt_auto_init_friend:
                if not config_gpt.gpt_init_friend_pernal_name:
                    logger.warning(f"检测到已开启好友初始化人设，但未配置具体人设名，类型 FriendAddNoticeEvent, id: {event.get_user_id()} 好友初始化人设失败")
                else:
                    logger.info(f"检测到已开启好友初始化人设，类型 FriendAddNoticeEvent, id: {event.get_user_id()} 即将好友初始化人设 {config_gpt.gpt_init_friend_pernal_name}")
                    await init_personal_api(chatbot,id=event.get_user_id(),personal_name=config_gpt.gpt_init_friend_pernal_name,type_from='private')
        elif isinstance(event,GroupIncreaseNoticeEvent):
            # onebot 群
            if event.get_user_id() == str(event.self_id):
                if config_gpt.gpt_auto_init_group:
                    if not config_gpt.gpt_init_group_pernal_name:
                        logger.warning(f"检测到已开启入群初始化人设，但未配置具体人设名，类型 GroupIncreaseNoticeEvent, id: {str(event.group_id)} 入群初始化人设失败")
                    else:
                        logger.info(f"检测到已开启入群初始化人设，类型 GroupIncreaseNoticeEvent, id: {str(event.group_id)} 即将入群初始化人设 {config_gpt.gpt_init_group_pernal_name}")
                        await init_personal_api(chatbot,id=str(event.group_id),personal_name=config_gpt.gpt_init_group_pernal_name,type_from='group')
        elif isinstance(event,FriendAddEvent):
            # QQ好友
            if config_gpt.gpt_auto_init_friend:
                if not config_gpt.gpt_init_friend_pernal_name:
                    logger.warning(f"检测到已开启好友初始化人设，但未配置具体人设名，类型 FriendAddEvent, id: {event.get_user_id()} 好友初始化人设失败")
                else:
                    logger.info(f"检测到已开启好友初始化人设，类型 FriendAddEvent, id: {event.get_user_id()} 即将好友初始化人设 {config_gpt.gpt_init_friend_pernal_name}")
                    await init_personal_api(chatbot,id=event.get_user_id(),personal_name=config_gpt.gpt_init_friend_pernal_name,type_from='QQprivate')
        elif isinstance(event,GuildMemberUpdateEvent):
            # QQ频道
            bot: QQBot = current_bot.get() # type: ignore
            if bot.self_info.id == event.op_user_id:
                if config_gpt.gpt_auto_init_group:
                    if not config_gpt.gpt_init_group_pernal_name:
                        logger.warning(f"检测到已开启频道初始化人设，但未配置具体人设名，类型 GuildMemberUpdateEvent, id: {event.guild_id} 频道初始化人设失败")
                    else:
                        logger.info(f"检测到已开启频道初始化人设，类型 GuildMemberUpdateEvent, id: {event.guild_id} 即将频道初始化人设 {config_gpt.gpt_init_group_pernal_name}")
                        await init_personal_api(chatbot,id=event.guild_id,personal_name=config_gpt.gpt_init_group_pernal_name,type_from='QQguild')
            

else:
    logger.warning("未检测到gpt账号信息，插件未成功加载")