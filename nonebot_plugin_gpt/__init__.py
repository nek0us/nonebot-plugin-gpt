from ChatGPTWeb import chatgpt
from nonebot.log import logger
from nonebot import on_command,on_message
from nonebot.adapters.onebot.v11 import Bot,Message,MessageEvent
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
    name="ChatGPT 浏览器聊天",
    description="通过浏览器使用 ChatGPT",
    usage="""
| 指令 | 权限 | 需要@ | 范围 | 说明 |
|:-----:|:----:|:----:|:----:|:----:|
| @bot 聊天内容... | 无/白名单 | 是 | 群聊/私聊 | @或者叫名+内容 开始聊天，随所有者白名单模式设置改变 |
| 初始化 | 无/白名单 | 是 | 群聊/私聊 | 初始化 <人设名> |
| 重置 | 无/白名单 | 是 | 群聊/私聊 | 回到初始化人设后的第二句话时 |
| 重置上一句 | 无/白名单 | 是 | 群聊/私聊 | 刷新上一句的回答 |
| 回到过去 | 无/白名单 | 是 | 群聊/私聊 | 回到过去 <对话序号/p_id/最后一次出现的关键词> ，回到括号内的对话时间点|
| 人设列表 | 无/白名单 | 是 | 群聊/私聊 | 查看可用人设列表 |
| 查看人设 | 无/白名单 | 是 | 群聊/私聊 | 查看人设的具体内容 |
| 添加人设 | 无/白名单 | 是 | 群聊/私聊 | 添加人设 (人设名) |
| 历史聊天 | 无/白名单 | 是 | 群聊/私聊 | 查看当前人格历史聊天记录 |
| 删除人设 | 超级管理员 | 是 | 群聊/私聊 | 删除人设 (人设名) |
| 工作状态 | 超级管理员 | 是 | 群聊/私聊 | 查看当前所有账号的工作状态 |
| 黑名单列表 | 超级管理员 | 是 | 群聊/私聊 | 查看黑名单列表 |
| 解黑 | 超级管理员 | 是 | 群聊/私聊 | 解黑 <账号> ，解除黑名单 |
| 白名单列表 | 超级管理员 | 是 | 群聊/私聊 | 查看白名单列表 |
| 添加白名单 | 超级管理员 | 是 | 群聊/私聊 | 添加白名单 <账号/群号> (个人/群) ，添加白名单，最后不写默认为群 |
| 删除白名单 | 超级管理员 | 是 | 群聊/私聊 | 删除白名单 <账号/群号> (个人/群) ，删除白名单，最后不写默认为群 |
    """,
    type="application",
    config=Config,
    homepage="https://github.com/nek0us/nonebot-plugin-gpt",
    supported_adapters={"~onebot.v11"},
    extra={
        "author":"nek0us",
        "version":__version__,
    }
)

if isinstance(config_gpt.gpt_session,list):
    chatbot = chatgpt(
        sessions = config_gpt.gpt_session,
        plugin = True,
        arkose_status = config_gpt.arkose_status,
        chat_file = data_dir,
        proxy = config_gpt.pywt_proxy,
        begin_sleep_time = config_gpt.begin_sleep_time
        )
    
    driver = get_driver()
    @driver.on_startup
    async def d():
        logger.info("登录GPT账号中")
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(chatbot.__start__(loop),loop)

    chat = on_message(priority=config_gpt.gpt_chat_priority,rule=gpt_rule) # rule=checker.cat_girl,
    @chat.handle()
    async def chat_handle(bot: Bot,event: MessageEvent,matcher: Matcher,text:Message = EventMessage()):
        await chat_msg(bot,event,matcher,chatbot,text)

        
                
    reset = on_command("reset",aliases={"重置记忆","重置","重置对话"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @reset.handle()
    async def reset_handle(bot: Bot,event: MessageEvent,matcher: Matcher):
        await reset_history(bot,event,matcher,chatbot)
    
            
    last = on_command("backlast",aliases={"重置上一句","重置上句"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @last.handle()
    async def last_handle(bot: Bot,event: MessageEvent,matcher: Matcher):
        await back_last(bot,event,matcher,chatbot)
            
            
    back = on_command("backloop",aliases={"回到过去"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @back.handle()
    async def back_handle(bot: Bot,event: MessageEvent,matcher: Matcher,arg: Message = CommandArg()):
        await back_anywhere(bot,event,matcher,chatbot,arg)
            

    init = on_command("init",aliases={"初始化","初始化人格","加载人格","加载预设"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @init.handle()
    async def init_handle(bot: Bot,event: MessageEvent,matcher: Matcher,arg :Message = CommandArg()):
        await init_gpt(bot,event,matcher,chatbot,arg)
        

    personality_list = on_command("人设列表",aliases={"预设列表","人格列表"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @personality_list.handle()
    async def personality_list_handle(bot: Bot,event: MessageEvent,matcher: Matcher):
        await ps_list(bot,event,matcher,chatbot)
                
            
    cat_personality = on_command("查看人设",aliases={"查看预设","查看人格"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @cat_personality.handle()
    async def cat_personality_handle(bot: Bot,event: MessageEvent,matcher: Matcher,arg: Message = CommandArg()):
        await cat_ps(bot,event,matcher,chatbot,arg)
                
                
    add_personality = on_command("添加人设",aliases={"添加预设","添加人格"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @add_personality.handle()
    async def add_personality_handle(event: MessageEvent,matcher: Matcher,status: T_State,arg :Message = CommandArg()):
        await add_ps1(event,matcher,status,arg)
        
    @add_personality.got("name",prompt="人设名叫什么？")
    async def add_personality_handle2(status: T_State,name: Message = Arg()):
        await add_ps2(status,name)
                
                
    @add_personality.got("r18",prompt="是R18人设吗？（回答 是 / 否)")
    async def add_personality_handle3(status: T_State,r18: Message = Arg()):
        await add_ps3(status,r18)

    @add_personality.got("open",prompt="要公开给其他人也可用吗？（回答 公开 / 私有)")
    async def add_personality_handle4(status: T_State,open: Message = Arg()):
        await add_ps4(status,open)
            
    @add_personality.got("value",prompt="请发送人设内容")
    async def add_personality_handle5(status: T_State,value: Message = Arg()):
        await add_ps5(status,value,chatbot)
        
    del_personality = on_command("删除人设",aliases={"删除人格","删除人设"},permission=SUPERUSER,rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @del_personality.handle()
    async def del_personality_handle(bot: Bot,event: MessageEvent,matcher: Matcher,status: T_State,arg :Message = CommandArg()):
        await del_ps(event,matcher,chatbot,arg)

    chat_history = on_command("history",aliases={"历史聊天","历史记录"},rule=gpt_rule,priority=config_gpt.gpt_command_priority,block=True)
    @chat_history.handle()
    async def chat_history_handle(bot: Bot,event: MessageEvent,matcher: Matcher):
        await chatmsg_history(bot,event,matcher,chatbot)

            
    status = on_command("gpt_status",aliases={"工作状态"},permission=SUPERUSER,priority=config_gpt.gpt_command_priority)
    @status.handle()
    async def status_handle(matcher: Matcher):
        await status_pic(matcher,chatbot)
        
    ban_list = on_command("黑名单列表",rule=to_me(),permission=SUPERUSER,priority=config_gpt.gpt_command_priority,block=True)
    @ban_list.handle()
    async def ban_list_handle(bot: Bot,event: MessageEvent,matcher: Matcher):
        await black_list(bot,event,matcher)
        
    ban_del = on_command("解黑",rule=to_me(),aliases={"解除黑名单","删除黑名单"},permission=SUPERUSER,priority=config_gpt.gpt_command_priority,block=True)
    @ban_del.handle()
    async def ban_del_handle(arg: Message = CommandArg()):
        await remove_ban_user(arg)
        
    add_white_cmd = on_command("添加白名单",aliases={"加白"},rule=to_me(),permission=SUPERUSER,priority=config_gpt.gpt_command_priority,block=True)
    @add_white_cmd.handle()
    async def add_white_handle(arg: Message = CommandArg()):
        await add_white_list(arg)
        
    del_white_cmd = on_command("删除白名单",aliases={"加白","解除白名单"},rule=to_me(),permission=SUPERUSER,priority=config_gpt.gpt_command_priority,block=True)
    @del_white_cmd.handle()
    async def del_white_handle(arg: Message = CommandArg()):
        await del_white_list(arg)
        
    white_list_cmd = on_command("白名单列表",rule=to_me(),permission=SUPERUSER,priority=config_gpt.gpt_command_priority,block=True)
    @white_list_cmd.handle()
    async def white_list_handle():
        await white_list()
else:
    logger.warning("未检测到gpt账号信息，插件未成功加载")