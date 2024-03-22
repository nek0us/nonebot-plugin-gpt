from ChatGPTWeb import chatgpt
from ChatGPTWeb.config import Personality
from nonebot.log import logger
from nonebot import on_command,on_message
from nonebot.adapters.onebot.v11 import Bot,Message,MessageEvent
from nonebot.adapters.qq.event import MessageEvent as QQMessageEvent
from nonebot.adapters.qq.event import AtMessageCreateEvent as QQAtMessageCreateEvent
from nonebot.adapters.qq.message import Message as QQMessage
from nonebot.matcher import Matcher
from nonebot.params import Arg, CommandArg,EventMessage
from nonebot.rule import to_me
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot import get_driver
from importlib.metadata import version
import asyncio


from .config import config_gpt,Config
from .source import *
from .api import *

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
| 初始化 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 初始化 <人设名> |
| 重置 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 回到初始化人设后的第二句话时 |
| 重置上一句 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 刷新上一句的回答 |
| 回到过去 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 回到过去 <对话序号/p_id/最后一次出现的关键词> ，回到括号内的对话时间点|
| 人设列表 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看可用人设列表 |
| 查看人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看人设的具体内容 |
| 添加人设 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 添加人设 (人设名) |
| 历史聊天 | 兼容 | 无/白名单 | 是 | 群聊/私聊/频道 | 查看当前人格历史聊天记录 |
| 删除人设 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除人设 (人设名) |
| 黑名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看黑名单列表 |
| 解黑 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 解黑 <账号> ，解除黑名单 |
| 白名单列表 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看白名单列表 |
| 添加白名单 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 添加白名单 <账号/群号> (个人/群) ，添加白名单，最后不写默认为群 |
| 删除白名单 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 删除白名单 <账号/群号> (个人/群) ，删除白名单，最后不写默认为群 |
| 工作状态 | 兼容 | 超级管理员/超管群 | 是 | 群聊/私聊/频道 | 查看当前所有账号的工作状态 |
| 获取本地id | qq | 无/白名单 | 是 | 群聊/频道 | 群聊内获取id |
| 生成cdk | qq | 超管群 | 是 | 群聊/频道 | 生成cdk <群号/其他信息>，以绑定信息方式生成白名单cdk |
| 出现吧 | qq | 无| 是 | 群聊/频道 | 出现吧 <cdk>，以绑定id形式使用cdk加入白名单 |
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
        httpx_status=config_gpt.gpt_httpx
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
    async def chat_handle(event: MessageEvent|QQMessageEvent,text:Message|QQMessage = EventMessage()):
        await chat_msg(event,chatbot,text)
                
    reset = on_command("reset",aliases={"重置记忆","重置","重置对话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @reset.handle()
    async def reset_handle(event: MessageEvent|QQMessageEvent):
        await reset_history(event,chatbot)
    
            
    last = on_command("backlast",aliases={"重置上一句","重置上句"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @last.handle()
    async def last_handle(event: MessageEvent|QQMessageEvent):
        await back_last(event,chatbot)
            
            
    back = on_command("backloop",aliases={"回到过去"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @back.handle()
    async def back_handle(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage = CommandArg()):
        await back_anywhere(event,chatbot,arg)
            

    init = on_command("init",aliases={"初始化","初始化人格","加载人格","加载预设"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @init.handle()
    async def init_handle(event: MessageEvent|QQMessageEvent,arg :Message|QQMessage = CommandArg()):
        await init_gpt(event,chatbot,arg)
        

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
    async def chat_history_handle(event: MessageEvent|QQMessageEvent):
        await chatmsg_history(event,chatbot)

            
    status = on_command("gpt_status",aliases={"工作状态"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @status.handle()
    async def status_handle(matcher: Matcher):
        await status_pic(matcher,chatbot)
        
    ban_list = on_command("黑名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @ban_list.handle()
    async def ban_list_handle(event: MessageEvent|QQMessageEvent):
        await black_list(event)
        
    ban_del = on_command("解黑",rule=gpt_manage_rule,aliases={"解除黑名单","删除黑名单"},priority=config_gpt.gpt_command_priority,block=True)
    @ban_del.handle()
    async def ban_del_handle(arg: Message|QQMessage = CommandArg()):
        await remove_ban_user(arg)
        
    add_white_cmd = on_command("添加白名单",aliases={"加白"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_white_cmd.handle()
    async def add_white_handle(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage = CommandArg()):
        await add_white_list(arg)
        
    del_white_cmd = on_command("删除白名单",aliases={"解除白名单","解白"},rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_white_cmd.handle()
    async def del_white_handle(arg: Message|QQMessage = CommandArg()):
        await del_white_list(arg)
        
    white_list_cmd = on_command("白名单列表",rule=gpt_manage_rule,priority=config_gpt.gpt_command_priority,block=True)
    @white_list_cmd.handle()
    async def white_list_handle():
        await white_list()
        
        
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

else:
    logger.warning("未检测到gpt账号信息，插件未成功加载")