from nonebot.adapters.onebot.v11 import MessageEvent,Message,GroupMessageEvent
from nonebot.matcher import Matcher,current_matcher
from nonebot.log import logger
from datetime import datetime
from typing import List, Literal,Dict
import json

from .source import banpath,ban_str_path,whitepath
from .config import config_gpt


async def gpt_rule(event: MessageEvent) -> bool:
    '''gpt事件匹配规则'''
    if event.to_me:
        ban_tmp = json.loads(banpath.read_text("utf-8"))
        if event.get_user_id() not in ban_tmp:
            # 不在黑名单？继续
            if not config_gpt.gpt_white_list_mode:
            # 关闭白名单？那放行
                return True
            # 开了白名单？那检查白名单
            white_tmp = json.loads(whitepath.read_text("utf-8"))
            # 白名单列表来
            if isinstance(event,GroupMessageEvent):
                if event.group_id in white_tmp["group"]:
                    return True
            else:
                if event.user_id in white_tmp["private"]:
                    return True
    return False

async def add_white(num: int,this_type: Literal["group", "private"] = "group"):
    '''添加白名单'''
    white_tmp: Dict[str, List[int]] = json.loads(whitepath.read_text("utf-8"))
    if num in white_tmp[this_type]:
        return "白名单已存在"
    white_tmp[this_type].append(num)
    whitepath.write_text(json.dumps(white_tmp))
    return "添加成功"

async def del_white(num: int,this_type: Literal["group", "private"] = "group"):
    '''删除白名单'''
    white_tmp: Dict[str, List[int]] = json.loads(whitepath.read_text("utf-8"))
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
async def ban_check(event: MessageEvent,matcher: Matcher,text: Message = Message()) -> None:
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
                tmp = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} 在 {'群' if isinstance(event,GroupMessageEvent) else '私聊'} {str(event.group_id) if isinstance(event,GroupMessageEvent) else str(event.user_id)} 中： {text.extract_plain_text()}"
                logger.info(f"屏蔽词黑名单添加：{event.get_user_id()} {tmp}")
                await add_ban(event.get_user_id(),tmp)   
                await matcher.finish()