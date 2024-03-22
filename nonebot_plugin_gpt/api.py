
from nonebot.adapters.onebot.v11 import Bot,Message,MessageSegment,MessageEvent,GroupMessageEvent,PrivateMessageEvent
from nonebot.matcher import Matcher,current_matcher,current_event
from nonebot.params import EventMessage
from ChatGPTWeb import chatgpt
from ChatGPTWeb.config import MsgData
from nonebot.log import logger
from nonebot.typing import T_State
from nonebot import require
require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_sendmsg_by_bots import tools
from more_itertools import chunked
import json
import re
import uuid

from .config import config_gpt,config_nb
from .source import *
from .check import *


bot_name = list(config_nb.nickname)


async def name_or_tome(event: MessageEvent) -> bool:
    '''
    ## if name return True
    ## if tome return False'''
    if [x for x in event.original_message if x.type == "at" and x.data["qq"] == str(event.self_id)]:
        return False
    else:
        return True

        
async def group_handle(data: MsgData,group_member: list) -> MsgData:
    qq_num_list = re.findall(r"[1-9][0-9]{4,10}",data.msg_recv) 
    if qq_num_list:
        for x in group_member:
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
    
async def chat_msg(event: MessageEvent|QQMessageEvent,chatbot: chatgpt,text: Message|QQMessage = EventMessage()):
    '''聊天处理'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher,text)
    data = MsgData()
    if config_gpt.gpt_chat_start and not config_gpt.gpt_chat_start_in_msg:
        chat_start = [gpt_start for gpt_start in config_gpt.gpt_chat_start if event.get_plaintext().startswith(gpt_start)]
        if chat_start:
            text = Message(text.extract_plain_text()[len(chat_start[0]):])
    text_handle = text.extract_plain_text()
    if isinstance(event,MessageEvent):
        if event.reply:
            # 被回复不回复
            if not config_gpt.gpt_replay_to_replay:
                await matcher.finish()
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
        data = await group_handle(data,await tools.get_group_member_list(group_id=event.group_id))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data.msg_send=event.raw_message
        data = await chatbot.continue_chat(data)
        
        tmp[str(event.user_id)] = data.conversation_id
        privatepath.write_text(json.dumps(tmp))
    elif isinstance(event,QQMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        id,value = await get_id_from_guild_group(event)
        if id in tmp:
            data.conversation_id = tmp[id]
        data.msg_send=text_handle
        data = await chatbot.continue_chat(data)
        tmp[id] = data.conversation_id
        grouppath.write_text(json.dumps(tmp))
        
    await ban_check(event,matcher,Message(data.msg_recv))
    
    if config_gpt.gpt_lgr_markdown and isinstance(event,MessageEvent):
        await tools.send_text2md(data.msg_recv,str(event.self_id))
        await matcher.finish()

    await matcher.finish(replace_name(data).msg_recv)
    

async def reset_history(event: MessageEvent|QQMessageEvent,chatbot: chatgpt):
    '''重置'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    data = MsgData() 
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
        data = await chatbot.back_init_personality(data)
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data = await chatbot.back_init_personality(data)
    elif isinstance(event,QQMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        id,value = await get_id_from_guild_group(event)
        if id in tmp:
            data.conversation_id = tmp[id]
        data = await chatbot.back_init_personality(data)
        
    await matcher.finish(replace_name(data).msg_recv)

async def back_last(event: MessageEvent|QQMessageEvent,chatbot: chatgpt):
    '''重置上一句'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    data = MsgData() 
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
            data.msg_send = "-1"
        data = await chatbot.back_chat_from_input(data)
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data.msg_send = "-1"
        data = await chatbot.back_chat_from_input(data)
    elif isinstance(event,QQMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        id,value = await get_id_from_guild_group(event)
        if id in tmp:
            data.conversation_id = tmp[id]
        data.msg_send = "-1"
        data = await chatbot.back_chat_from_input(data)
    await matcher.finish(replace_name(data).msg_recv)
    
async def back_anywhere(event: MessageEvent|QQMessageEvent,chatbot:chatgpt,arg: Message|QQMessage):
    '''回到过去'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    data = MsgData() 
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
            data.msg_send = arg.extract_plain_text()
        data = await chatbot.back_chat_from_input(data)
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        data.msg_send = arg.extract_plain_text()
        data = await chatbot.back_chat_from_input(data)
    
    elif isinstance(event,QQMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        id,value = await get_id_from_guild_group(event)
        if id in tmp:
            data.conversation_id = tmp[id]
            data.msg_send = arg.extract_plain_text()
            data = await chatbot.back_chat_from_input(data)
            
    await matcher.finish(replace_name(data).msg_recv)
    
async def init_gpt(event: MessageEvent|QQMessageEvent,chatbot:chatgpt,arg :Message|QQMessage):
    '''初始化'''
    matcher: Matcher = current_matcher.get()
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
            elif isinstance(event,PrivateMessageEvent):
                tmp = json.loads(privatepath.read_text("utf-8"))
                if event.get_user_id() in tmp:
                    data.conversation_id = tmp[event.get_user_id()]
            elif isinstance(event,QQMessageEvent):
                tmp = json.loads(grouppath.read_text("utf-8"))
                id,value = await get_id_from_guild_group(event)
                if id in tmp:
                    data.conversation_id = tmp[id]
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
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
        await ban_check(event,matcher,Message(data.msg_recv))
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf-8"))
        tmp[str(event.user_id)] = data.conversation_id
        privatepath.write_text(json.dumps(tmp))
        await ban_check(event,matcher,Message(data.msg_recv))
    elif isinstance(event,QQMessageEvent):
        tmp = json.loads(grouppath.read_text("utf-8"))
        id,value = await get_id_from_guild_group(event)
        tmp[id] = data.conversation_id
        grouppath.write_text(json.dumps(tmp))
        await ban_check(event,matcher,QQMessage(data.msg_recv))
        
    if isinstance(event,QQMessageEvent):
        await matcher.finish(replace_name(data).msg_recv)
    else:
        msg = Message(MessageSegment.node_custom(user_id=event.self_id,nickname=arg.extract_plain_text(),content=Message(replace_name(data).msg_recv)))
        if isinstance(event,GroupMessageEvent):
            await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=msg)
        else:
            await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=msg)
    await matcher.finish()
    
async def ps_list(event: MessageEvent|QQMessageEvent,chatbot: chatgpt):
    '''人设列表'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    person_list = [MessageSegment.node_custom(user_id=event.self_id,nickname="0",content=Message(MessageSegment.text("序号  人设名  r18  公开")))]
    person_type = json.loads(personpath.read_text("utf8"))
    if person_type == {}:
        await matcher.finish("还没有人设")
    for index,x in enumerate(chatbot.personality.init_list):
        r18 = "是" if person_type[x.get('name')]['r18'] else "否"
        open = "否" if person_type[x.get('name')]['open'] else "是"
        person_list.append(MessageSegment.node_custom(user_id=event.self_id,nickname="0",content=Message(MessageSegment.text(f"{(index+1):02}  {x.get('name')}  {r18}  {open} "))))

    if isinstance(event,GroupMessageEvent):
        await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=person_list)
    else:
        await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=person_list)

    await matcher.finish()
                
async def cat_ps(event: MessageEvent|QQMessageEvent,chatbot: chatgpt,arg: Message|QQMessage):
    '''查看人设'''
    matcher: Matcher = current_matcher.get()
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
        if isinstance(event,MessageEvent):    
            msg = Message(MessageSegment.node_custom(user_id=event.self_id,nickname=arg.extract_plain_text(),content=Message(value)))
            if isinstance(event,GroupMessageEvent):
                await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=msg)
            else:
                await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=msg)
        else:
            await matcher.finish(value)
    else:
        await matcher.finish("好像没有输入名字哦")
        
async def add_ps1(event: MessageEvent|QQMessageEvent,status: T_State,arg :Message|QQMessage):
    '''添加人设，步骤1'''
    matcher: Matcher = current_matcher.get()
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
        
async def add_ps2(status: T_State,name: Message|QQMessage):
    '''添加人设，步骤2'''
    if name:
        status["name"] = name
    else:
        matcher: Matcher = current_matcher.get()
        await matcher.finish("输入错误了，添加结束。")   
        
async def add_ps3(status: T_State,r18: Message|QQMessage):
    '''添加人设，步骤3'''
    if r18.extract_plain_text() == "是":
        status["r18"] = True
    elif r18.extract_plain_text() == "否":
        status["r18"] = False
    else:
        matcher: Matcher = current_matcher.get()
        await matcher.finish("输入错误了，添加结束。")
        
async def add_ps4(status: T_State,open: Message|QQMessage):
    '''添加人设，步骤4'''
    if open.extract_plain_text() == "公开" :
        status["open"] = ""
    elif open.extract_plain_text() == "私有":
        status["open"] = status["id"]
    else:
        matcher: Matcher = current_matcher.get()
        await matcher.finish("输入错误了，添加结束。")
        
async def add_ps5(status: T_State,value: Message|QQMessage,chatbot: chatgpt):
    '''添加人设，步骤5'''
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
    
    
async def add_default_ps(chatbot: chatgpt):
    '''添加人设'''
    personality = {
        "name":"默认",
        "r18":False,
        "open":"",
        "value":"你好",
        
    }
    person_type = json.loads(personpath.read_text("utf8"))
    if personality["name"] not in person_type:
        await chatbot.add_personality(personality)
    person_type = json.loads(personpath.read_text("utf8"))
    person_type[personality["name"]] = {
            "r18":personality["r18"],
            "open":personality["open"]
        }
    
    personpath.write_text(json.dumps(person_type))
    
    
async def del_ps(event: MessageEvent|QQMessageEvent,chatbot: chatgpt,arg :Message|QQMessage):
    '''删除人设'''
    matcher: Matcher = current_matcher.get()
    person_type = json.loads(personpath.read_text("utf8"))
    try:
        del person_type[arg.extract_plain_text()]
        personpath.write_text(json.dumps(person_type))
    except:
        await matcher.finish("没有找到这个人设")
    await matcher.finish(await chatbot.del_personality(arg.extract_plain_text()))
    
async def chatmsg_history(event: MessageEvent|QQMessageEvent,chatbot: chatgpt):
    '''历史记录'''
    data = MsgData()
    matcher: Matcher = current_matcher.get()
    if isinstance(event,GroupMessageEvent):
        tmp = json.loads(grouppath.read_text("utf8"))
        if str(event.group_id) in tmp:
            data.conversation_id = tmp[str(event.group_id)]
        else:
            await matcher.finish("还没有聊天记录")    
            
        chat_his = [MessageSegment.node_custom(user_id=10000,nickname=str(index + 1),content=Message(history) )  for index,history in enumerate(await chatbot.show_chat_history(data))]
        # chat_his = await node_msg(10000,await chatbot.show_chat_history(data))
        if len(chat_his) > 100:
            chunks = list(chunked(chat_his,100))
            for list_value in chunks: 
                await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=list_value)
        else:
            await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=chat_his)
        
    elif isinstance(event,PrivateMessageEvent):
        tmp = json.loads(privatepath.read_text("utf8"))
        if event.get_user_id() in tmp:
            data.conversation_id = tmp[event.get_user_id()]
        else:
            await matcher.finish("还没有聊天记录")  
        chat_his = [MessageSegment.node_custom(user_id=10000,nickname=str(index + 1),content=Message(history) )  for index,history in enumerate(await chatbot.show_chat_history(data))]
        
        if len(chat_his) > 200:
            chunks = list(chunked(chat_his,200))
            for list_value in chunks: 
                await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=list_value) 
        else:
            await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=chat_his)
    elif isinstance(event,QQMessageEvent):
        tmp = json.loads(grouppath.read_text("utf8"))
        id,value = await get_id_from_guild_group(event)
        if id in tmp:
            data.conversation_id = tmp[id]
        else:
            await matcher.finish("还没有聊天记录")  
        res = await chatbot.show_chat_history(data)
        await matcher.finish('\n'.join(res))
        
    await matcher.finish()
    
    
async def status_pic(matcher: Matcher,chatbot: chatgpt):
    '''工作状态'''
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
    
    event = current_event.get()
    if isinstance(event,QQGroupAtMessageCreateEvent):
        #qq适配器的QQ群，暂不支持直接发送图片    
        await matcher.finish(''.join(msg.replace(".com","")))
    elif isinstance(event,MessageEvent):
        await matcher.finish(MessageSegment.image(file=await md_to_pic(msg)))
    else:
        await matcher.finish(QQMessageSegment.file_image(await md_to_pic(msg)))
    
async def black_list(event: MessageEvent|QQMessageEvent):
    '''黑名单列表'''
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    msg = "|账户|内容|\n|:------:|:------:|\n"
    for x in ban_tmp:
        msg += f"|{x}|{ban_tmp[x][0]}|\n"
    if isinstance(event,QQGroupAtMessageCreateEvent):
        #qq适配器的QQ群，暂不支持直接发送图片    
        await matcher.finish(''.join(msg))
    elif isinstance(event,MessageEvent):
        await matcher.finish(MessageSegment.image(file=await md_to_pic(msg)))
    else:
        await matcher.finish(QQMessageSegment.file_image(await md_to_pic(msg)))
    
async def remove_ban_user(arg: Message|QQMessage):
    ''''解黑'''
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    try:
        del ban_tmp[arg.extract_plain_text()]
        banpath.write_text(json.dumps(ban_tmp))
    except:
        await matcher.finish("失败")
    
    await matcher.finish("成功")
    
async def add_white_list(arg: Message|QQMessage|str):
    '''加白 传入消息则消息为目标群号，传str则它为群号'''
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    id = ""
    this_type = "group"
    event = current_event.get()
    if isinstance(event,QQGroupAtMessageCreateEvent):
        this_type = "qqgroup"
    elif isinstance(event,QQAtMessageCreateEvent):
        this_type = "qqguild"
    if isinstance(arg,str):
        id = arg
    else:
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
        
    await matcher.finish(await add_white(id, this_type))
    
async def del_white_list(arg: Message|QQMessage|str):
    '''删除白名单'''
    matcher: Matcher = current_matcher.get()
    id = ""
    this_type = "group"
    event = current_event.get()
    if isinstance(event,QQGroupAtMessageCreateEvent):
        this_type = "qqgroup"
    elif isinstance(event,QQAtMessageCreateEvent):
        this_type = "qqguild"
    if isinstance(arg,str):
        id = arg
    else:
        if " " in arg.extract_plain_text():
            sp = arg.extract_plain_text().split(" ")
            id = sp[0]
            this_type = sp[1]
            if this_type not in ["group","private","群","个人"]:
                await matcher.finish(f"白名单类型错误了，仅支持 群 / 个人，不输入默认为群")
            this_type = "group" if this_type == "群" else "private"
        else:
            id = arg.extract_plain_text()
        
    await matcher.finish(await del_white(id, this_type))
    
async def white_list():
    '''获取白名单列表'''
    matcher: Matcher = current_matcher.get()
    white_tmp = json.loads(whitepath.read_text("utf-8"))
    msg = "|类型|账号|\n|:------:|:------:|\n"
    for x in white_tmp:
        for id in white_tmp[x]:
            msg += f"|{x}|{str(id)}|\n"
    event = current_event.get()
    if isinstance(event,QQGroupAtMessageCreateEvent):
        #qq适配器的QQ群，暂不支持直接发送图片    
        await matcher.finish(''.join(msg))
    elif isinstance(event,MessageEvent):
        await matcher.finish(MessageSegment.image(file=await md_to_pic(msg)))
    else:
        await matcher.finish(QQMessageSegment.file_image(await md_to_pic(msg)))
    
async def random_cdk_api(arg: QQMessage):
    '''生成用户可用的cdk'''
    matcher: Matcher = current_matcher.get()
    if not arg.extract_plain_text():
        logger.debug("cdk需要申请人信息")
        await matcher.finish("cdk需要申请人信息")
    key = uuid.uuid4().hex
    cdk_list = json.loads(cdklistpath.read_text())
    cdk_source = json.loads(cdksource.read_text())
    cdk_list[key] = None
    cdk_source[key] = arg.extract_plain_text()
    cdklistpath.write_text(json.dumps(cdk_list))
    cdksource.write_text(json.dumps(cdk_source))
    # 生成cdk 和 将该cdk绑定到申请人（qq或者群），作为记录
    await matcher.finish(key)
    
async def add_checker_api(event: QQMessageEvent,arg: QQMessage):
    '''QQ适配器用户自添加白名单'''
    matcher: Matcher = current_matcher.get()
    # 先验cdk列表
    cdk_list = json.loads(cdklistpath.read_text())
    key = arg.extract_plain_text()
    if key not in cdk_list:
        # 没这个key
        await matcher.finish()
    if cdk_list[key]:
        # 这个key绑定过了
        await matcher.finish()
    id,value = await get_id_from_guild_group(event)
    cdk_list[key] = id   
    cdklistpath.write_text(json.dumps(cdk_list))
    
    # 再弄白名单列表
    await add_white_list(id)