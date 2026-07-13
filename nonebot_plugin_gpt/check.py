from nonebot.adapters.onebot.v11 import MessageEvent,Message,GroupMessageEvent,PrivateMessageEvent
from nonebot.adapters.qq.event import MessageEvent as QQMessageEvent
from nonebot.adapters.qq.event import AtMessageCreateEvent as QQAtMessageCreateEvent
from nonebot.adapters.qq.event import GroupAtMessageCreateEvent as QQGroupAtMessageCreateEvent
from nonebot.adapters.qq.message import Message as QQMessage
from nonebot.adapters.qq.message import MessageSegment as QQMessageSegment
from nonebot.adapters import Event
from nonebot.matcher import Matcher,current_matcher
from nonebot.log import logger
from datetime import datetime
from typing import Any, List, Literal,Dict,Tuple
import json

from .source import banpath,ban_str_path,whitepath,plusstatus
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
async def get_id_from_all(event: Event) -> Tuple[str, str]:
    '''return id,value'''
    if isinstance(event,GroupMessageEvent):
        id = str(event.group_id)
        value = "group"
    elif isinstance(event,QQMessageEvent):
        id,value = await get_id_from_guild_group(event)
    elif isinstance(event, MessageEvent):
        id = str(event.user_id)
        value = "private"
    else:
        id = event.get_session_id()
        value = "session"
    return id,value


def _event_plain_text(event: Event) -> str:
    """读取适配器通用的纯文本消息，缺失时安全降级为空字符串。"""
    get_plaintext = getattr(event, "get_plaintext", None)
    if callable(get_plaintext):
        return str(get_plaintext())
    get_message = getattr(event, "get_message", None)
    if callable(get_message):
        message = get_message()
        extract_plain_text = getattr(message, "extract_plain_text", None)
        if callable(extract_plain_text):
            return str(extract_plain_text())
    return ""


def _message_plain_text(message: Any) -> str:
    """读取跨适配器消息对象的纯文本。"""
    extract_plain_text = getattr(message, "extract_plain_text", None)
    if callable(extract_plain_text):
        return str(extract_plain_text())
    return str(message or "")


def _addressed_to_bot(event: Event) -> bool:
    """NoneBot 适配器未提供 to_me 时按未提及处理。"""
    return bool(getattr(event, "to_me", False))


def _is_private_session(event: Event) -> bool:
    """识别适配器未设置 to_me 的稳定私聊会话。"""
    return ":private:" in event.get_session_id().lower()
    
async def plus_status(event: Event) -> bool:
    if _addressed_to_bot(event):
        if event.get_user_id() in config_nb.superusers:
            return True
        ban_tmp = json.loads(banpath.read_text("utf-8"))
        if event.get_user_id() not in ban_tmp:
            if not config_gpt.gptplus_white_list_mode:
            # 关闭gpt4白名单？那放行
                return True
            # 开了白名单？那检查plus白名单
            white_plus_tmp = json.loads(plusstatus.read_text("utf-8"))
            id,value = await get_id_from_all(event)
            if id in white_plus_tmp or event.get_session_id() in white_plus_tmp:
                return True
    return False


async def gpt_rule(event: Event) -> bool:
    '''gpt事件匹配规则'''
    if _addressed_to_bot(event) or _is_private_session(event) or [gpt_start for gpt_start in config_gpt.gpt_chat_start if _event_plain_text(event).startswith(gpt_start)]:
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
            if id in white_tmp.get(value, []) or event.get_session_id() in white_tmp.get("session", []):
                return True
            if event.get_user_id() in white_tmp.get("private", []):
                return True
    return False

async def gpt_manage_rule(event: Event) -> bool:
    '''管理事件匹配'''
    if _addressed_to_bot(event) or _is_private_session(event):
        if event.get_user_id() in config_nb.superusers:
            return True
        id,value = await get_id_from_all(event)
        if id in config_gpt.gpt_manage_ids or event.get_session_id() in config_gpt.gpt_manage_ids:
            return True
    return False

async def add_white(num: str,this_type: Literal["group", "private", "qqgroup", "qqguild", "session"] = "group",plus: bool = False):
    '''添加白名单'''
    white_tmp: Dict[str, List[str]] =  json.loads(whitepath.read_text("utf-8")) 
    white_tmp.setdefault(this_type, [])
    if num in white_tmp[this_type]:
        return "白名单已存在"
    if plus:
        plus_tmp = json.loads(plusstatus.read_text("utf-8")) 
        plus_tmp[num] = "text-davinci-002-render-sha"
        plusstatus.write_text(json.dumps(plus_tmp))
    white_tmp[this_type].append(num)
    whitepath.write_text(json.dumps(white_tmp))
    return "添加成功"

async def del_white(num: str,this_type: Literal["group", "private", "qqgroup", "qqguild", "session"] = "group"):
    '''删除白名单'''
    white_tmp: Dict[str, List[str]] = json.loads(whitepath.read_text("utf-8"))
    if num not in white_tmp.get(this_type, []):
        return "不在白名单中"
    plus_tmp = json.loads(plusstatus.read_text("utf-8")) 
    if num in plus_tmp:
        del plus_tmp[num]
    plusstatus.write_text(json.dumps(plus_tmp))
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
async def ban_check(event: Event,matcher: Matcher,text: Any = None) -> None:
    '''检测黑名单'''
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    if event.get_user_id() in ban_tmp:
        # 被ban了不回复
        await matcher.finish()
    ban_str_tmp = ban_str_path.read_text("utf-8").splitlines()
    plain_text = _message_plain_text(text)
    if plain_text:
        for ban_str in ban_str_tmp:
            if ban_str in plain_text:
                # 触发屏蔽词
                current_time = datetime.now()
                id,value = await get_id_from_all(event)
                tmp = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} 在 {value} {id} 中触发屏蔽词 {ban_str}\n {plain_text}"
                logger.info(f"屏蔽词黑名单触发，屏蔽词：{ban_str}\n触发人：{event.get_user_id()}\n原语句：{tmp}")
                await add_ban(event.get_user_id(),tmp)   
                await matcher.finish()
