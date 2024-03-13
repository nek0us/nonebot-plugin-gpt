from nonebot.adapters.onebot.v11 import MessageEvent,Message,GroupMessageEvent,PrivateMessageEvent
from nonebot.adapters.qq.event import MessageEvent as QQMessageEvent
from nonebot.adapters.qq.event import AtMessageCreateEvent as QQAtMessageCreateEvent
from nonebot.adapters.qq.event import GroupAtMessageCreateEvent as QQGroupAtMessageCreateEvent
from nonebot.adapters.qq.message import Message as QQMessage
from nonebot.adapters.qq.message import MessageSegment as QQMessageSegment
from nonebot.matcher import Matcher,current_matcher
from nonebot.log import logger
from datetime import datetime
from typing import List, Literal,Dict
import json

from .source import banpath,ban_str_path,whitepath
from .config import config_gpt,config_nb

# 获取id    
async def get_id_from_guild_group(event: QQMessageEvent):
    '''QQ适配器获取id（群号频道号）'''
    if isinstance(event,QQAtMessageCreateEvent):
        id = event.guild_id
        value = "qqguild"
    else:
        id = event.group_id # type: ignore
        value = "qqgroup"
    return id,value 

# 返回类型
async def get_id_from_all(event: MessageEvent|QQMessageEvent):
    '''return id,value'''
    if isinstance(event,GroupMessageEvent):
        id = str(event.group_id)
        value = "group"
    elif isinstance(event,PrivateMessageEvent):
        id = str(event.user_id)
        value = "private"
    elif isinstance(event,QQMessageEvent):
        id,value = await get_id_from_guild_group(event)
    else:
        id,value = "",""
    return id,value


async def gpt_rule(event: MessageEvent|QQMessageEvent) -> bool:
    '''gpt事件匹配规则'''
    if event.to_me or [gpt_start for gpt_start in config_gpt.gpt_chat_start if event.get_plaintext().startswith(gpt_start)]:
        ban_tmp = json.loads(banpath.read_text("utf-8"))
        if event.get_user_id() not in ban_tmp:
            # 不在黑名单？继续
            if not config_gpt.gpt_white_list_mode:
            # 关闭白名单？那放行
                return True
            # 开了白名单？那检查白名单
            white_tmp = json.loads(whitepath.read_text("utf-8"))
            # 白名单列表来
            id,value = await get_id_from_all(event)
            if id in white_tmp[value]:
                return True
            if event.get_user_id() in white_tmp["private"]:
                return True
    return False

async def gpt_manage_rule(event: MessageEvent|QQMessageEvent) -> bool:
    '''管理事件匹配'''
    if event.to_me:
        if isinstance(event,MessageEvent):
            if event.get_user_id() in config_nb.superusers:
                return True
        else:
            id,value = await get_id_from_guild_group(event)
            if id in config_gpt.gpt_manage_ids:
                return True
    return False

async def add_white(num: str,this_type: Literal["group", "private", "qqgroup", "qqguild"] = "group"):
    '''添加白名单'''
    white_tmp: Dict[str, List[str]] = json.loads(whitepath.read_text("utf-8"))
    if num in white_tmp[this_type]:
        return "白名单已存在"
    white_tmp[this_type].append(num)
    whitepath.write_text(json.dumps(white_tmp))
    return "添加成功"

async def del_white(num: str,this_type: Literal["group", "private", "qqgroup", "qqguild"] = "group"):
    '''删除白名单'''
    white_tmp: Dict[str, List[str]] = json.loads(whitepath.read_text("utf-8"))
    if num not in white_tmp[this_type]:
        return "不在白名单中"
    white_tmp[this_type].remove(num)
    whitepath.write_text(json.dumps(white_tmp))
    return "删除成功"

async def add_ban(user:str,value:str):
    '''添加黑名单'''
    tmp = json.loads(banpath.read_text("utf-8"))
    if user not in tmp:
        tmp[user] = []
    tmp[user].append(value)
    banpath.write_text(json.dumps(tmp))
    

# 黑名单关键词检索
async def ban_check(event: MessageEvent|QQMessageEvent,matcher: Matcher,text: Message|QQMessage = Message()) -> None:
    '''检测黑名单'''
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    if event.get_user_id() in ban_tmp:
        # 被ban了不回复
        await matcher.finish()
    ban_str_tmp = ban_str_path.read_text("utf-8").splitlines()
    if text.extract_plain_text():
        for ban_str in ban_str_tmp:
            if ban_str in text.extract_plain_text():
                # 触发屏蔽词
                current_time = datetime.now()
                id,value = await get_id_from_all(event)
                tmp = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} 在 {value} {id} 中： {text.extract_plain_text()}"
                logger.info(f"屏蔽词黑名单添加：{event.get_user_id()} {tmp}")
                await add_ban(event.get_user_id(),tmp)   
                await matcher.finish()