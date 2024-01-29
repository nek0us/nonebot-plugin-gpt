
from nonebot.adapters.onebot.v11 import Bot,Message,MessageSegment,MessageEvent,GroupMessageEvent,PrivateMessageEvent
from nonebot.matcher import Matcher,current_matcher
from nonebot.params import EventMessage
from ChatGPTWeb import chatgpt
from ChatGPTWeb.config import MsgData
from nonebot.log import logger
from nonebot.typing import T_State
from nonebot import require
require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import md_to_pic
from more_itertools import chunked
import nonebot
import json
import re

from .config import config_gpt
from .source import *
from .check import *

config_dev = nonebot.get_driver().config
bot_name = list(config_dev.nickname)

       
async def node_msg(user_id,plain_text:list,name: str|list|None = None):
    '''以转发方式返回聊天记录'''
    if not plain_text:
        plain_text.append("无")
    msg = []
    if type(name) == str:
        msg = [
        {
            "type": "node",
            "data": {
                "name": name,
                "uin": int(user_id),
                "content": [
                    {
                        "type": "text",
                        "data": {
                            "text": x
                        }
                    }
                ]
            }
        } for x in plain_text]
    elif name == None:
        msg = [
        {
            "type": "node",
            "data": {
                "name": str(index),
                "uin": int(user_id),
                "content": [
                    {
                        "type": "text",
                        "data": {
                            "text": x
                        }
                    }
                ]
            }
        } for index,x in enumerate(plain_text)]
    elif type(name) == list:
        msg = [
        {
            "type": "node",
            "data": {
                "name": n,
                "uin": int(user_id),
                "content": [
                    {
                        "type": "text",
                        "data": {
                            "text": x
                        }
                    }
                ]
            }
        } for x,n in zip(plain_text,name)]    
    return msg    

async def name_or_tome(event: MessageEvent) -> bool:
    '''
    ## if name return True
    ## if tome return False'''
    if [x for x in event.original_message if x.type == "at" and x.data["qq"] == str(event.self_id)]:
        return False
    else:
        return True

        
async def group_handle(data: MsgData,group_info: list) -> MsgData:
    qq_num_list = re.findall(r"[1-9][0-9]{4,10}",data.msg_recv) 
    if qq_num_list:
        for x in group_info:
            for y in qq_num_list:
                if x["user_id"] == int(y):
                    if x["card"]:
                        data.msg_recv = data.msg_recv.replace(y,x["card"])
                    else:
                        data.msg_recv = data.msg_recv.replace(y,x["nickname"])
    data.msg_recv = data.msg_recv.replace("编号","")
    return data
           
def replace_name(data: MsgData) -> MsgData:
    for name in bot_name:
        data.msg_recv = data.msg_recv.replace(f"{name}：","").replace(f"{name}:","")
    return data
    
async def chat_msg(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot: chatgpt,text: Message = EventMessage()):
    await ban_check(event,matcher,text)
    if event.reply:
        # 被回复不回复
        if not config_gpt.gpt_replay_to_replay:
            await matcher.finish()
    data = MsgData()
    text_handle = text.extract_plain_text()
    if await name_or_tome(event):
        if len(event.raw_message) > 6:
            for name in bot_name:
                if name in event.raw_message[:6]:
                    
                    text_handle = f"{name} {text}"
        else:
            for name in bot_name:
                if name in event.raw_message:
                    text_handle = f"{name} {text}"
            
    else:
        if not text.extract_plain_text():
            # text 为空
            text_handle = f"{bot_name[0]}" 
        else:
            text_handle = text.extract_plain_text()
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
        if config_gpt.group_chat:
            data.msg_send = f'{event.get_user_id()}对你说：{text_handle}'
        else:
            data.msg_send=text_handle
        # 替换qq
        data.msg_send=data.msg_send.replace("CQ:at,qq=","")
        data = await chatbot.continue_chat(data)
        tmp[str(event.group_id)] = data.conversation_id
        grouppath.write_text(json.dumps(tmp))
        data = await group_handle(data,await bot.call_api('get_group_member_list',**{"group_id":event.group_id}))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data.msg_send=event.raw_message
        data = await chatbot.continue_chat(data)
        
        tmp[str(event.user_id)] = data.conversation_id
        privatepath.write_text(json.dumps(tmp))
        
    await ban_check(event,matcher,Message(data.msg_recv))
    
    await matcher.finish(replace_name(data).msg_recv)
    

async def reset_history(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot: chatgpt):
    await ban_check(event,matcher)
    data = MsgData() 
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
        data = await chatbot.back_init_personality(data)
        data = await group_handle(data,await bot.call_api('get_group_member_list',**{"group_id":event.group_id}))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data = await chatbot.back_init_personality(data)
    
    await matcher.finish(replace_name(data).msg_recv)

async def back_last(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot: chatgpt):
    await ban_check(event,matcher)
    data = MsgData() 
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
            data.msg_send = "-1"
        data = await chatbot.back_chat_from_input(data)
        data = await group_handle(data,await bot.call_api('get_group_member_list',**{"group_id":event.group_id}))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data.msg_send = "-1"
        data = await chatbot.back_chat_from_input(data)
    
    await matcher.finish(replace_name(data).msg_recv)
    
async def back_anywhere(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot:chatgpt,arg: Message):
    await ban_check(event,matcher)
    data = MsgData() 
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
            data.msg_send = arg.extract_plain_text()
        data = await chatbot.back_chat_from_input(data)
        data = await group_handle(data,await bot.call_api('get_group_member_list',**{"group_id":event.group_id}))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data.msg_send = arg.extract_plain_text()
        data = await chatbot.back_chat_from_input(data)
    
    await matcher.finish(replace_name(data).msg_recv)
    
async def init_gpt(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot:chatgpt,arg :Message):
    await ban_check(event,matcher)
    data = MsgData()
    if arg.extract_plain_text() == '':
        arg = Message("默认")
    person_type = json.loads(personpath.read_text("utf8"))
    if " " in arg.extract_plain_text():
        data.msg_send = arg.extract_plain_text().split(" ")[0]
        
        if person_type[data.msg_send]['open'] != '':
            if event.get_user_id() != person_type[data.msg_send]['open']:
                await matcher.finish("别人的私有人设不可以用哦")
        
        if arg.extract_plain_text().split(" ")[1] == "继续":
            if isinstance(event,GroupMessageEvent):
                tmp = json.loads(grouppath.read_text("utf-8"))
                if str(event.group_id) in tmp:
                    data.conversation_id = tmp[str(event.group_id)]
            else:
                tmp = json.loads(privatepath.read_text("utf-8"))
                if event.get_user_id() in tmp:
                    data.conversation_id = tmp[event.get_user_id()]
    else:
        data.msg_send = arg.extract_plain_text()
        if person_type[data.msg_send]['open'] != '':
            if event.get_user_id() != person_type[data.msg_send]['open']:
                await matcher.finish("别人的私有人设不可以用哦")
    #data.msg_send = arg.extract_plain_text()
    if isinstance(event,GroupMessageEvent):
        if person_type[data.msg_send]['r18']:
            if event.sender.role != "owner" and event.sender.role != "admin":
                await matcher.finish("在群里仅群管理员可初始化r18人设哦")
    data = await chatbot.init_personality(data)
    if isinstance(event,GroupMessageEvent):
        
        tmp = json.loads(grouppath.read_text("utf-8"))
        tmp[str(event.group_id)] = data.conversation_id
        grouppath.write_text(json.dumps(tmp))
        data = await group_handle(data,await bot.call_api('get_group_member_list',**{"group_id":event.group_id}))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        tmp[str(event.user_id)] = data.conversation_id
        privatepath.write_text(json.dumps(tmp))

    await ban_check(event,matcher,Message(data.msg_recv))
    msg = await node_msg(event.user_id,[replace_name(data).msg_recv])
    if isinstance(event,GroupMessageEvent):
        await bot.send_forward_msg(group_id=event.group_id,messages=msg)
    else:
        await bot.send_forward_msg(user_id=event.user_id,messages=msg)
    await matcher.finish()
    
async def ps_list(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot: chatgpt):
    await ban_check(event,matcher)
    person_list = ["序号  人设名  r18  公开"]
    person_type = json.loads(personpath.read_text("utf8"))
    if person_type == {}:
        await matcher.finish("还没有人设")
    for index,x in enumerate(chatbot.personality.init_list):
        r18 = "是" if person_type[x.get('name')]['r18'] else "否"
        open = "否" if person_type[x.get('name')]['open'] else "是"
        person_list.append(f"{(index+1):02}  {x.get('name')}  {r18}  {open} ")
        
    person_list = await node_msg(event.user_id,person_list)
    
    if isinstance(event,GroupMessageEvent):
        await bot.send_forward_msg(group_id=event.group_id,messages=person_list)
    else:
        await bot.send_forward_msg(user_id=event.user_id,messages=person_list)
    await matcher.finish()
                
async def cat_ps(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot: chatgpt,arg: Message):
    await ban_check(event,matcher)
    if arg.extract_plain_text():
        person_type = json.loads(personpath.read_text("utf8"))
        if arg.extract_plain_text() not in person_type:
            await matcher.finish("没有找到哦，请检查名字是否正确")
        # if event.get_user_id() != person_type[arg.extract_plain_text()]['open'] or '' != person_type[arg.extract_plain_text()]['open']:
        #     await matcher.finish("别人的私有人设不可以看哦")
        if person_type[arg.extract_plain_text()]['open'] != '':
            if event.get_user_id() != person_type[arg.extract_plain_text()]['open']:
                await matcher.finish("别人的私有人设不可以用哦")
        value = chatbot.personality.get_value_by_name(arg.extract_plain_text())
        if not value:
            await matcher.finish("没有找到哦，请检查名字是否正确")
        msg = await node_msg(event.user_id,[value],"人设详情")
        if isinstance(event,GroupMessageEvent):
            await bot.send_forward_msg(group_id=event.group_id,messages=msg)
        else:
            await bot.send_forward_msg(user_id=event.user_id,messages=msg)
    else:
        await matcher.finish("好像没有输入名字哦")
        
async def add_ps1(event: MessageEvent,matcher: Matcher,status: T_State,arg :Message):
    await ban_check(event,matcher)
    status["id"] = event.get_user_id()
    try:
        if arg.extract_plain_text():
            status["name"] = arg.extract_plain_text()
            
            ban_str_tmp = ban_str_path.read_text("utf-8").splitlines()
            if str(status["name"]) in  ban_str_tmp:
                # 触发屏蔽词
                await add_ban(event.get_user_id(),str(status["name"]))   
                await matcher.finish("检测到屏蔽词，已屏蔽")
            if len(status["name"]) > 15:
                await matcher.finish("名字不可以超过15字")
            elif len(status["name"]) == 0:
                await matcher.finish("名字不可以为空")
            if status["name"] in json.loads(personpath.read_text("utf8")):
                await matcher.finish("这个人设名已存在哦，换一个吧")
        else:
            pass
    except Exception as e:
        logger.info(e)
        
async def add_ps2(status: T_State,name: Message):
    if name:
        status["name"] = name
    else:
        matcher: Matcher = current_matcher.get()
        await matcher.finish("输入错误了，添加结束。")   
        
async def add_ps3(status: T_State,r18: Message):
    if r18.extract_plain_text() == "是":
        status["r18"] = True
    elif r18.extract_plain_text() == "否":
        status["r18"] = False
    else:
        matcher: Matcher = current_matcher.get()
        await matcher.finish("输入错误了，添加结束。")
        
async def add_ps4(status: T_State,open: Message):
    if open.extract_plain_text() == "公开" :
        status["open"] = ""
    elif open.extract_plain_text() == "私有":
        status["open"] = status["id"]
    else:
        matcher: Matcher = current_matcher.get()
        await matcher.finish("输入错误了，添加结束。")
        
async def add_ps5(status: T_State,value: Message,chatbot: chatgpt):
    status["value"] = value
    personality = {
        "name":str(status["name"]),
        "r18":status["r18"],
        "open":status["open"],
        "value":str(status["value"]),
        
    }
    matcher: Matcher = current_matcher.get()
    ban_str_tmp = ban_str_path.read_text("utf-8").splitlines()
    for x in ban_str_tmp:
        if x in str(status["value"]):
            # 触发屏蔽词 
            await matcher.finish("存在违禁词")
    await chatbot.add_personality(personality)
    person_type = json.loads(personpath.read_text("utf8"))
    person_type[personality["name"]] = {
            "r18":personality["r18"],
            "open":personality["open"]
        }
    
    personpath.write_text(json.dumps(person_type))
    
    await matcher.finish(await chatbot.show_personality_list())
    
async def del_ps(event: MessageEvent,matcher: Matcher,chatbot: chatgpt,arg :Message):
    await ban_check(event,matcher)
    person_type = json.loads(personpath.read_text("utf8"))
    try:
        del person_type[arg.extract_plain_text()]
        personpath.write_text(json.dumps(person_type))
    except:
        await matcher.finish("没有找到这个人设")
    await matcher.finish(await chatbot.del_personality(arg.extract_plain_text()))
    
async def chatmsg_history(bot: Bot,event: MessageEvent,matcher: Matcher,chatbot: chatgpt):
    await ban_check(event,matcher)
    data = MsgData()
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
        else:
            await matcher.finish("还没有聊天记录")    
        chat_his = await node_msg(event.user_id,await chatbot.show_chat_history(data))
        if len(chat_his) > 100:
            chunks = list(chunked(chat_his,100))
            for list_value in chunks: 
                await bot.send_group_forward_msg(group_id=event.group_id,messages=list_value)   # type: ignore 
        else:
            await bot.send_forward_msg(group_id=event.group_id,messages=chat_his) 
        
    else:
        tmp = json.loads(privatepath.read_text("utf8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        else:
            await matcher.finish("还没有聊天记录")  
        chat_his = await node_msg(event.user_id,await chatbot.show_chat_history(data))
        
        if len(chat_his) > 200:
            chunks = list(chunked(chat_his,200))
            for list_value in chunks: 
                await bot.send_private_forward_msg(user_id=event.user_id,messages=list_value)   # type: ignore 
        else:
            await bot.send_forward_msg(user_id=event.user_id,messages=chat_his)
        
    await matcher.finish()
    
    
async def status_pic(matcher: Matcher,chatbot: chatgpt):
    try:
        tmp = await chatbot.token_status()
        if len(tmp["token"]) != len(tmp["work"]):
            await matcher.finish(f"似乎还没启动完咩")
    except Exception as e:
        logger.debug(e)
        await matcher.finish()
    msg = "|序号|账户|存活|工作状态|历史会话|\n|:----:|:------:|:------:|:------:|:------:|\n"
    for index,x in enumerate(tmp["token"]):
        if len(tmp['cid_num']) < len(tmp["token"]):
            for num in range(0,len(tmp["token"])-len(tmp['cid_num'])):
                tmp['cid_num'] += ['0']
        msg += f"|{(index+1):03}|{tmp['account'][index]}|{x}|{tmp['work'][index]}|  {int(tmp['cid_num'][index]):03}  |\n"
    
    await matcher.finish(MessageSegment.image(file=await md_to_pic(msg)))
    
async def black_list(bot: Bot,event: MessageEvent,matcher: Matcher):
    # 待续
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    msg = "|账户|内容|\n|:------:|:------:|\n"
    for x in ban_tmp:
        msg += f"|{x}|{ban_tmp[x][0]}|\n"
    await matcher.finish(MessageSegment.image(file=await md_to_pic(msg)))
    
async def remove_ban_user(arg: Message):
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    try:
        del ban_tmp[arg.extract_plain_text()]
        banpath.write_text(json.dumps(ban_tmp))
    except:
        await matcher.finish("失败")
    
    await matcher.finish("成功")
    
async def add_white_list(arg: Message):
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    id = ""
    this_type = "group"
    if " " in arg.extract_plain_text():
        sp = arg.extract_plain_text().split(" ")
        id = sp[0]
        this_type = sp[1]
        if this_type not in ["group","private","群","个人"]:
            await matcher.finish(f"白名单类型错误了，仅支持 群 / 个人，不输入默认为群")
        this_type = "group" if this_type == "群" else "private"
    else:
        id = arg.extract_plain_text()
        
    if id in ban_tmp:
        await matcher.finish(f"对方在黑名单中哦，真的要继续吗？")
        
    await matcher.finish(await add_white(int(id), this_type))
    
async def del_white_list(arg: Message):
    matcher: Matcher = current_matcher.get()
    id = ""
    this_type = "group"
    if " " in arg.extract_plain_text():
        sp = arg.extract_plain_text().split(" ")
        id = sp[0]
        this_type = sp[1]
        if this_type not in ["group","private","群","个人"]:
            await matcher.finish(f"白名单类型错误了，仅支持 群 / 个人，不输入默认为群")
        this_type = "group" if this_type == "群" else "private"
    else:
        id = arg.extract_plain_text()
        
    await matcher.finish(await del_white(int(id), this_type))
    
async def white_list():
    matcher: Matcher = current_matcher.get()
    white_tmp = json.loads(whitepath.read_text("utf-8"))
    msg = "|类型|账号|\n|:------:|:------:|\n"
    for x in white_tmp:
        for id in white_tmp[x]:
            msg += f"|{'群' if x == 'group' else '个人'}|{str(id)}|\n"
    await matcher.finish(MessageSegment.image(file=await md_to_pic(msg)))