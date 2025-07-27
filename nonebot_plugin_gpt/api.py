

from nonebot.adapters.onebot.v11 import Message,MessageSegment,MessageEvent,GroupMessageEvent,PrivateMessageEvent,Bot
from nonebot.matcher import Matcher,current_matcher,current_event
from nonebot.params import EventMessage
from ChatGPTWeb import chatgpt
from ChatGPTWeb.config import MsgData,IOFile,get_model_by_key,all_models_keys,all_models_values,all_free_models_values
from nonebot.log import logger
from nonebot.typing import T_State
from nonebot import require
from nonebot_plugin_sendmsg_by_bots import tools
from httpx import AsyncClient
from more_itertools import chunked
from base64 import b64encode
from typing import Literal
from filetype import guess
import json
import re
import uuid
from datetime import datetime

from .config import config_gpt,config_nb
from .source import (
    grouppath,
    group_conversations_path,
    privatepath,
    private_conversations_path,
    mdstatus,
    personpath,
    whitepath,
    cdklistpath,
    cdksource,
    ban_str_path,
    banpath,
    plusstatus,
    
)
from .check import (
    QQMessageEvent,
    QQMessage,
    QQGroupAtMessageCreateEvent,
    QQAtMessageCreateEvent,
    QQMessageSegment,
    get_id_from_guild_group,
    get_id_from_all,
    ban_check,
    add_ban,
    add_white,
    del_white,
    
    
)
require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import md_to_pic  # noqa: E402


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
                        if data.msg_raw:
                            data.msg_raw = [msg.replace(y,x["card"]) for msg in data.msg_raw]
                        data.msg_recv = data.msg_recv.replace(y,x["card"])
                    else:
                        if data.msg_raw:
                            data.msg_raw = [x.replace(y,x["nickname"]) for x in data.msg_raw]
                        data.msg_recv = data.msg_recv.replace(y,x["nickname"])
    data.msg_recv = data.msg_recv.replace("编号","")
    return data
           
def replace_name(data: MsgData) -> MsgData:
    for name in bot_name:
        if data.msg_raw:
            data.msg_raw = [x.replace(f"{name}：","").replace(f"{name}:","") for x in data.msg_raw]
        data.msg_recv = data.msg_recv.replace(f"{name}：","").replace(f"{name}:","")
    return data

def get_c_id(id:str, data: MsgData,c_type: Literal['group','private'] = 'group') -> MsgData:
    group_conversations = json.loads(group_conversations_path.read_text())
    private_conversations = json.loads(private_conversations_path.read_text())

    if c_type == 'group':
        tmp = json.loads(grouppath.read_text("utf-8"))
        if id in group_conversations:
            for c in group_conversations[id]:
                if tmp[id] == c["conversation_id"]:
                    data.title = c["conversation_name"]
    else:
        tmp = json.loads(privatepath.read_text("utf-8"))
        if id in private_conversations:
            for c in private_conversations[id]:
                if tmp[id] == c["conversation_id"]:
                    data.title = c["conversation_name"]


    # if data.gpt_model == "gpt-4":
    #     if id + '-gpt-4' in tmp:
    #         data.conversation_id = tmp[id + '-gpt-4']
    # elif data.gpt_model == "gpt-4o":
    #     if id + '-gpt-4o' in tmp:
    #         data.conversation_id = tmp[id + '-gpt-4o']
    # else:
    #     if id in tmp:
    #         data.conversation_id = tmp[id]
    
    # 不再根据模型隔离会话，同一个会话内也可以切换模型，兼容官网改动
    if id in tmp:
        data.conversation_id = tmp[id]

    return data

def set_c_id(id:str, data: MsgData,c_type: Literal['group','private'] = 'group'):
    group_conversations = json.loads(group_conversations_path.read_text())
    private_conversations = json.loads(private_conversations_path.read_text())
    if c_type == 'group':
        tmp = json.loads(grouppath.read_text("utf-8"))
        if id in group_conversations:
            for c in group_conversations[id]:
                if data.conversation_id == c["conversation_id"]:
                    if data.title:
                        c["conversation_name"] = data.title
        
    else:
        tmp = json.loads(privatepath.read_text("utf-8"))
        if id in private_conversations:
            for c in private_conversations[id]:
                if data.conversation_id == c["conversation_id"]:
                    if data.title:
                        c["conversation_name"] = data.title

    # if data.gpt_model == "gpt-4":
    #     tmp[id + '-gpt-4'] = data.conversation_id
    # elif data.gpt_model == "gpt-4o":
    #     tmp[id + '-gpt-4o'] = data.conversation_id
    # # pass switch 4.1?
    # else:
    #     tmp[id] = data.conversation_id

    # 不再根据模型隔离会话，同一个会话内也可以切换模型，兼容官网改动
    tmp[id] = data.conversation_id

    if c_type == 'group':
        grouppath.write_text(json.dumps(tmp)) 
        group_conversations_path.write_text(json.dumps(group_conversations))
    else:
        privatepath.write_text(json.dumps(tmp)) 
        private_conversations_path.write_text(json.dumps(private_conversations))

def upgrade_model(model: str) -> str:
    if model in all_free_models_values() and model in all_models_values() and model != all_free_models_values()[0]:
        return all_free_models_values()[0]
    return model


    
    
async def chat_msg(bot: Bot,event: MessageEvent|QQMessageEvent,chatbot: chatgpt,text: Message|QQMessage = EventMessage()):
    '''聊天处理'''
    matcher: Matcher = current_matcher.get()

    # bot1 = current_bot
    # # bots = bot1.name 
    # b = bot1.get()
    # bots = get_bots()
    # bbb = T_BotConnectionHook
    await ban_check(event,matcher,text)
    data = MsgData()
    data.web_search = True
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
    # 检测plus模型状态
    plus_tmp = json.loads(plusstatus.read_text())
    id,value = await get_id_from_all(event)
    if id in plus_tmp and plus_tmp['status']:
        data.gpt_model = plus_tmp[id]
        if config_gpt.gpt_force_upgrade_model:
            data.gpt_model = upgrade_model(data.gpt_model)

    # 图片附加消息检测，free账户也可用但额度很低
    if config_gpt.gpt_free_image or id in plus_tmp:
        msgs = event.get_message()
        imgs = [msg for msg in msgs if msg.type == "image"]
        if imgs:
            for img_msg in imgs:
                async with AsyncClient() as client:
                    res = await client.get(img_msg.data['url'])
                    data.upload_file.append(IOFile(content=res.content,name=img_msg.data['url']))

    if isinstance(event,GroupMessageEvent):
        data = get_c_id(str(event.group_id),data,'group')
        if config_gpt.group_chat:
            data.msg_send = f'{event.get_user_id()}对你说：{text_handle}'
        else:
            data.msg_send=text_handle
        # 替换qq
        data.msg_send=data.msg_send.replace("CQ:at,qq=","")
        data = await chatbot.continue_chat(data)
        if not data.error_info or data.status:
            set_c_id(str(event.group_id),data,'group')
            # group_member = await bot.call_api('get_group_member_list',**{"group_id":event.group_id})
            # data = await group_handle(data,group_member)
            data = await group_handle(data,await tools.get_group_member_list(group_id=event.group_id))
        
    elif isinstance(event,PrivateMessageEvent):
        data = get_c_id(event.get_user_id(),data,'private')
        data.msg_send=event.raw_message
        data = await chatbot.continue_chat(data)
        if not data.error_info or data.status:
            set_c_id(event.get_user_id(),data,'private')
    elif isinstance(event,QQMessageEvent):
        id,value = await get_id_from_guild_group(event)
        data = get_c_id(id,data,'group')
        data.msg_send=text_handle
        data = await chatbot.continue_chat(data)
        if not data.error_info or data.status:
            set_c_id(id,data,'group')
        
    if data.error_info and not data.msg_recv:
        data.msg_recv = data.error_info


    
    await ban_check(event,matcher,Message(data.msg_recv))

    imgs = []
    if data.img_list:
        logger.debug(f"检测到gpt消息存在图片链接\n {''.join(data.img_list)}")
        async with AsyncClient(proxy=config_gpt.gpt_proxy) as client:
            for img_url in data.img_list:
                try:
                    res = await client.get(img_url)
                    if res.status_code == 200:
                        mime = guess(res.content)
                        if"image" in mime.mime:
                            logger.debug(f"链接{img_url}为图片，准备装填")
                            imgs.append(res.content)
                except Exception as e:
                    logger.warning(f"获取图片 {img_url} 出现异常：{e}")
    send_md_status = True
    if config_gpt.gpt_lgr_markdown and isinstance(event,MessageEvent):
        md_status_tmp = json.loads(mdstatus.read_text())
        if isinstance(event,PrivateMessageEvent):
            if event.get_user_id() not in md_status_tmp['private']:
                send_md_status = False
        else:
            id,value = await get_id_from_all(event)
            if id not in md_status_tmp['group']:
                send_md_status = False
    else:
        send_md_status = False

    msg = replace_name(data).msg_raw[0] + replace_name(data).msg_raw[2] if replace_name(data).msg_raw and len(data.msg_raw) > 2 else replace_name(data).msg_recv

    if send_md_status and isinstance(event,MessageEvent):
        await tools.send_text2md(msg,str(event.self_id))
        if imgs:
            await matcher.send(Message([MessageSegment.image(file=img) for img in imgs]))
        await matcher.finish()
    elif send_md_status and isinstance(event,QQMessageEvent):
        #TODO QQ适配器 md模板等兼容发送，待续
        pass
    elif not send_md_status and isinstance(event,QQMessageEvent):
        # QQ适配器正常消息
        msg_img = Message([QQMessageSegment.file_image(b64encode(img).decode('utf-8')) for img in imgs])
    elif not send_md_status and isinstance(event,MessageEvent):
        # onebot适配器正常消息
        msg_img = [MessageSegment.image(file=img) for img in imgs]
    if config_gpt.gpt_url_replace and isinstance(event,QQMessageEvent):
        if data.msg_raw and len(data.msg_raw) > 2:
            data.msg_raw[0] = replace_dot_in_domain(data.msg_raw[0])
            data.msg_raw[2] = replace_dot_in_domain(data.msg_raw[2])
        else:
            msg = replace_dot_in_domain(msg)
    
    if data.msg_raw:
        if len(data.msg_raw)>1:
            try:
                # msg_md_pic = await md_to_pic(''.join(data.msg_raw))
                msg_md_pic = await chatbot.md2img(''.join(data.msg_raw))
            except Exception as e:
                logger.warning(f"获取元数据转md图片出错")
            if not send_md_status and isinstance(event,QQMessageEvent):
                # QQ适配器正常消息
                md_img = QQMessageSegment.file_image(b64encode(msg_md_pic).decode('utf-8'))
            else:
                md_img = MessageSegment.image(file=msg_md_pic)
            end_msg = md_img # data.msg_raw[0] + md_img + data.msg_raw[2]
        else:
            end_msg = msg
    else:
        end_msg = msg
        
    if imgs:
        all_msg = Message(end_msg)+Message(msg_img)
    else:
        all_msg = Message(end_msg)
    await matcher.finish(all_msg)
    

async def reset_history(event: MessageEvent|QQMessageEvent,chatbot: chatgpt,text:Message|QQMessage = EventMessage()):
    '''重置'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    data = MsgData() 
    # 检测plus模型状态
    plus_tmp = json.loads(plusstatus.read_text())
    id,value = await get_id_from_all(event)
    if id in plus_tmp and plus_tmp['status']:
        data.gpt_model = plus_tmp[id]
        if config_gpt.gpt_force_upgrade_model:
            data.gpt_model = upgrade_model(data.gpt_model)
    if isinstance(event,PrivateMessageEvent):
        data = get_c_id(id,data,'private')
    else:  
        data = get_c_id(id,data,'group')  
    data = await chatbot.back_init_personality(data)  
    if isinstance(event,GroupMessageEvent):
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
    if config_gpt.gpt_url_replace and isinstance(event,QQMessageEvent):
        data.msg_recv = replace_dot_in_domain(data.msg_recv)
    await matcher.finish(replace_name(data).msg_recv)

async def back_last(event: MessageEvent|QQMessageEvent,chatbot: chatgpt,text:Message|QQMessage = EventMessage()):
    '''重置上一句'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    data = MsgData() 
    # 检测plus模型状态
    plus_tmp = json.loads(plusstatus.read_text())
    id,value = await get_id_from_all(event)
    if id in plus_tmp and plus_tmp['status']:
        data.gpt_model = plus_tmp[id]
        if config_gpt.gpt_force_upgrade_model:
            data.gpt_model = upgrade_model(data.gpt_model)
    if isinstance(event,PrivateMessageEvent):
        data = get_c_id(id,data,'private')
    else:  
        data = get_c_id(id,data,'group')  
    data.msg_send = "-1"
    data = await chatbot.back_chat_from_input(data)
    if isinstance(event,GroupMessageEvent):
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
    if config_gpt.gpt_url_replace and isinstance(event,QQMessageEvent):
        data.msg_recv = replace_dot_in_domain(data.msg_recv)
    await matcher.finish(replace_name(data).msg_recv)
    
async def back_anywhere(event: MessageEvent|QQMessageEvent,chatbot:chatgpt,arg: Message|QQMessage):
    '''回到过去'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    data = MsgData() 
    # 检测plus模型状态
    plus_tmp = json.loads(plusstatus.read_text())
    id,value = await get_id_from_all(event)
    if id in plus_tmp and plus_tmp['status']:
        data.gpt_model = plus_tmp[id]
        if config_gpt.gpt_force_upgrade_model:
            data.gpt_model = upgrade_model(data.gpt_model)
    if isinstance(event,PrivateMessageEvent):
        data = get_c_id(id,data,'private')
    else:  
        data = get_c_id(id,data,'group')  
    data.msg_send = arg.extract_plain_text()
    data = await chatbot.back_chat_from_input(data)
    if isinstance(event,GroupMessageEvent):
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
    if config_gpt.gpt_url_replace and isinstance(event,QQMessageEvent):
        data.msg_recv = replace_dot_in_domain(data.msg_recv)
    await matcher.finish(replace_name(data).msg_recv)
    
async def init_gpt(event: MessageEvent|QQMessageEvent,chatbot:chatgpt,arg :Message|QQMessage,plus: bool = False):
    '''初始化'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    data = MsgData()
    if plus:
        data.gpt_plus = True
        logger.info(f"当前为plus初始化")
    if arg.extract_plain_text() == '':
        arg = Message("默认")
    # 检测plus模型状态
    plus_tmp = json.loads(plusstatus.read_text())
    id,value = await get_id_from_all(event)
    if id in plus_tmp and plus_tmp['status']:
        data.gpt_model = plus_tmp[id]
        if config_gpt.gpt_force_upgrade_model:
            data.gpt_model = upgrade_model(data.gpt_model)
    person_type = json.loads(personpath.read_text("utf8"))
    if " " in arg.extract_plain_text():
        data.msg_send = arg.extract_plain_text().split(" ")[0]
        
        if person_type[data.msg_send]['open'] != '':
            if event.get_user_id() != person_type[data.msg_send]['open']:
                await matcher.finish("别人的私有人设不可以用哦")
        
        if arg.extract_plain_text().split(" ")[1] == "继续":
            if isinstance(event,PrivateMessageEvent):
                data = get_c_id(id,data,'private')
            else:  
                data = get_c_id(id,data,'group')  
    else:
        data.msg_send = arg.extract_plain_text()
        if person_type[data.msg_send]['open'] != '':
            if event.get_user_id() != person_type[data.msg_send]['open']:
                await matcher.finish("别人的私有人设不可以用哦")
    
    if isinstance(event,GroupMessageEvent):
        if person_type[data.msg_send]['r18']:
            if event.sender.role != "owner" and event.sender.role != "admin":
                await matcher.finish("在群里仅群管理员可初始化r18人设哦")
    data = await chatbot.init_personality(data)
    
    if not data.msg_recv:
        await matcher.finish( f"初始化失败，错误为：\n{data.error_info}")
    if isinstance(event,PrivateMessageEvent):
        set_c_id(id,data,'private')
    else: 
        set_c_id(id,data,'group')    
    if isinstance(event,GroupMessageEvent):
        data = await group_handle(data,await tools.get_group_member_list(event.group_id))
    await ban_check(event,matcher,Message(data.msg_recv))
    
    # 保存会话标题 来源信息
    current_time = datetime.now()

    conversation_info = {
        "init_time": current_time.strftime('%Y-%m-%d %H:%M:%S'),
        "conversation_name": data.title,
        "conversation_id": data.conversation_id,
        "from_email": data.from_email,
    }

    group_conversations = json.loads(group_conversations_path.read_text())
    private_conversations = json.loads(private_conversations_path.read_text())

    if isinstance(event,QQMessageEvent):
        if id not in group_conversations:
            group_conversations[id] = [conversation_info]
        else:
            group_conversations[id].insert(0,conversation_info)
            if len(group_conversations[id]) > 30:
                group_conversations[id].pop()
        group_conversations_path.write_text(json.dumps(group_conversations))

        if config_gpt.gpt_url_replace:
            data.msg_recv = replace_dot_in_domain(data.msg_recv)
        await matcher.finish(replace_name(data).msg_recv)
    else:
        msg = Message(MessageSegment.node_custom(user_id=event.self_id,nickname=arg.extract_plain_text(),content=Message(replace_name(data).msg_recv)))
        if isinstance(event,GroupMessageEvent):
            if id not in group_conversations:
                group_conversations[id] = [conversation_info]
            else:
                group_conversations[id].insert(0,conversation_info)
                if len(group_conversations[id]) > 30:
                    group_conversations[id].pop()
            group_conversations_path.write_text(json.dumps(group_conversations))
            await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=msg,bot_id=str(event.self_id))
        else:
            if id not in private_conversations:
                private_conversations[id] = [conversation_info]
            else:
                private_conversations[id].insert(0,conversation_info)
                if len(private_conversations[id]) > 30:
                    private_conversations[id].pop()
            private_conversations_path.write_text(json.dumps(private_conversations))
            await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=msg,bot_id=str(event.self_id))
    await matcher.finish()
    
async def ps_list(event: MessageEvent|QQMessageEvent,chatbot: chatgpt):
    '''人设列表'''
    matcher: Matcher = current_matcher.get()
    await ban_check(event,matcher)
    if isinstance(event,MessageEvent):
        person_list = [MessageSegment.node_custom(user_id=event.self_id,nickname="0",content=Message(MessageSegment.text("序号  人设名  r18  公开")))]
    else:
        person_list = "\n|序号|人设名|r18|公开|\n|:----:|:------:|:------:|:------:|\n"
    person_type = json.loads(personpath.read_text("utf8"))
    if person_type == {}:
        await matcher.finish("还没有人设")
    for index,x in enumerate(chatbot.personality.init_list):
        r18 = "是" if person_type[x.get('name')]['r18'] else "否"
        open = "否" if person_type[x.get('name')]['open'] else "是"
        if isinstance(event,MessageEvent):
            person_list.append(MessageSegment.node_custom(user_id=event.self_id,nickname="0",content=Message(MessageSegment.text(f"{(index+1):02}  {x.get('name')}  {r18}  {open} ")))) # type: ignore
        else:
            person_list += f"|{(index+1):03}|{x.get('name')}|{r18}|{open}|\n" # type: ignore
            
    if isinstance(event,MessageEvent):        
        if isinstance(event,GroupMessageEvent):
            await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=person_list,bot_id=str(event.self_id)) # type: ignore
        else:
            await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=person_list,bot_id=str(event.self_id)) # type: ignore
    else:
        if isinstance(event,QQGroupAtMessageCreateEvent):
            await matcher.finish(person_list.replace("|:----:|:------:|:------:|:------:|\n","")) # type: ignore
        img = await md_to_pic(person_list) # type: ignore
        # img = await chatbot.md2img(person_list)
        await matcher.finish(QQMessageSegment.file_image(img))
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
                await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=msg,bot_id=str(event.self_id))
            else:
                await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=msg,bot_id=str(event.self_id))
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
    event = current_event.get()
    matcher: Matcher = current_matcher.get()
    if name:
        if type(name) == str:
            pass
        else:
            
            if name.extract_plain_text():
                status["name"] = name.extract_plain_text()
                
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
                status["name"] = name.extract_plain_text()
            else:
                await matcher.finish("名字不可以为空（也许是与bot同名了）")  
    else:
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
    except Exception:
        await matcher.finish("没有找到这个人设")
    await matcher.finish(await chatbot.del_personality(arg.extract_plain_text()))
    
async def chatmsg_history(bot: Bot,event: MessageEvent|QQMessageEvent,chatbot: chatgpt,text:Message|QQMessage = EventMessage()):
    '''历史记录'''
    data = MsgData()
    # 检测plus模型状态
    # plus_tmp = json.loads(plusstatus.read_text())
    id,value = await get_id_from_all(event)
    # if id in plus_tmp and plus_tmp['status']:
    #     data.gpt_model = plus_tmp[id]
    if isinstance(event,PrivateMessageEvent):
        data = get_c_id(id,data,'private')
    else:  
        data = get_c_id(id,data,'group')  
    matcher: Matcher = current_matcher.get()
    if not data.conversation_id:
        await matcher.finish("还没有聊天记录")  

    def to_num(snum: str) -> int:
        num = 0
        try:
            num = int(snum)
        except:
            logger.debug(f"{snum} not int")
        return num
    left_num = 1
    right_num = None
    if "-" in text.extract_plain_text() and text.extract_plain_text().count("-") == 1:
        if text.extract_plain_text().split("-")[0]:
            num = to_num(text.extract_plain_text().split("-")[0])
            left_num = num if num != 0 else 1
        if text.extract_plain_text().split("-")[1]:
            num = to_num(text.extract_plain_text().split("-")[1])
            right_num = num if num != 0 else 1
    elif ":" in text.extract_plain_text() and text.extract_plain_text().count(":") == 1:
        if text.extract_plain_text().split(":")[0]:
            num = to_num(text.extract_plain_text().split(":")[0])
            left_num = num if num != 0 else 1
        if text.extract_plain_text().split(":")[1]:
            num = to_num(text.extract_plain_text().split(":")[1])
            right_num = num if num != 0 else 1
    else:
        if text.extract_plain_text:
            num = to_num(text.extract_plain_text())
            left_num = num if num!= 0 else 1
            right_num = num+1 if num!=0 else None

    chat_his = [MessageSegment.node_custom(user_id=event.self_id,nickname=str(index),content=Message(f"### index `{history['index']}`\n---\n```next_msg_id\n{history['next_msg_id']}\n---\n```Q\n{history['Q']}\n---\n```A\n{history['A']}```"))  for index,history in enumerate(await chatbot.show_chat_history(data))][left_num:right_num]
    if chat_his == []:
        await matcher.finish("还没有开始聊天")
    if isinstance(event,GroupMessageEvent):
        # await bot.send_group_forward_msg(group_id=event.group_id, messages=chat_his)
        await tools.send_group_forward_msg_by_bots_once(group_id=event.group_id,node_msg=chat_his,bot_id=str(event.self_id))
    elif isinstance(event,PrivateMessageEvent): 
        # await bot.send_private_forward_msg(user_id=event.user_id, messages=chat_his)
        await tools.send_private_forward_msg_by_bots_once(user_id=event.user_id,node_msg=chat_his,bot_id=str(event.self_id))

    elif isinstance(event,QQMessageEvent):
        res = await chatbot.show_chat_history(data)
        if config_gpt.gpt_url_replace:
            send_msg = replace_dot_in_domain('\n'.join(res))
        else:
            send_msg = '\n'.join(res)
        await matcher.finish(send_msg)
        
    await matcher.finish()
    
async def chatmsg_history_tree(event: MessageEvent|QQMessageEvent,chatbot: chatgpt,text:Message|QQMessage = EventMessage()):
    '''历史记录树'''
    data = MsgData()
    id,value = await get_id_from_all(event)
    if isinstance(event,PrivateMessageEvent):
        data = get_c_id(id,data,'private')
    else:  
        data = get_c_id(id,data,'group')  
    matcher: Matcher = current_matcher.get()
    if not data.conversation_id:
        await matcher.finish("还没有聊天记录")  
    tree = await chatbot.show_history_tree_md(msg_data=data)
    # pic = await md_to_pic(tree)
    pic = await chatbot.md2img(tree)
    await matcher.finish(MessageSegment.image(file=pic))
    
async def status_pic(matcher: Matcher,chatbot: chatgpt):
    '''工作状态'''
    try:
        tmp = await chatbot.token_status()
        if len(tmp["token"]) != len(tmp["work"]):
            await matcher.finish("似乎还没启动完咩")
    except Exception as e:
        logger.debug(e)
        await matcher.finish()
    msg = f"""### 白名单模式：`{'已开启' if config_gpt.gpt_white_list_mode else '已关闭'}`
---
### plus白名单模式：`{'已开启' if config_gpt.gptplus_white_list_mode else '已关闭'}`
---
### 多人识别：`{'已开启' if config_gpt.group_chat else '已关闭'}`
---
"""
    msg += "\n|序号|存活|工作状态|历史会话|plus|账户|\n|:----:|:------:|:------:|:------:|:------:|:------:|\n"
    for index,x in enumerate(tmp["token"]):
        if len(tmp['cid_num']) < len(tmp["token"]):
            for num in range(0,len(tmp["token"])-len(tmp['cid_num'])):
                tmp['cid_num'] += ['0']
        msg += f"|{(index+1):03}|{x}|{tmp['work'][index]}|  {int(tmp['cid_num'][index]):03}|{tmp['plus'][index]}|{tmp['account'][index]}|\n"
    
    event = current_event.get()
    img = await md_to_pic(msg)
    # img = await chatbot.md2img(msg)
    if isinstance(event,QQGroupAtMessageCreateEvent):  
        await matcher.finish(QQMessageSegment.file_image(b64encode(img).decode('utf-8'))) # type: ignore
    elif isinstance(event,MessageEvent):
        await matcher.finish(MessageSegment.image(file=img))
    else:
        await matcher.finish(QQMessageSegment.file_image(img))
    
async def black_list(chatbot: chatgpt,event: MessageEvent|QQMessageEvent,arg :Message|QQMessage):
    '''黑名单列表'''
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    msgs_head = ["\n|账户|内容|","|:------:|:------:|"]
    msgs = []
    if arg.extract_plain_text():
        if arg.extract_plain_text() in ban_tmp:
            f_tmp = ban_tmp[arg.extract_plain_text()][0].replace('"',r'\"').replace("\n","  ")
            msgs.append(f"|{arg.extract_plain_text()}|{f_tmp}|")
    else:
        for x in ban_tmp:
            f_tmp = ban_tmp[x][0].replace('"',r'\"').replace("\n","  ")
            msgs.append(f"|{x}|{f_tmp}|")
    imgs = []
    if len(msgs) > 100:
        chunks = list(chunked(msgs,100))
        for chunk in chunks:
            tmp = msgs_head.copy()
            tmp.extend(chunk)
            imgs.append(await md_to_pic('\n'.join(tmp), width=650))
    else:
        imgs.append(await md_to_pic('\n'.join(msgs_head + msgs), width=650))
    if isinstance(event,QQGroupAtMessageCreateEvent):
        #qq适配器的QQ群，暂不支持直接发送图片 (x 现在能发了)   
        msg = QQMessage([QQMessageSegment.file_image(b64encode(img).decode('utf-8')) for img in imgs]) # type: ignore
        await matcher.finish(msg) # type: ignore
    elif isinstance(event,MessageEvent):
        msg = Message([MessageSegment.image(file=img) for img in imgs])
        await matcher.finish(msg)
    else:
        msg = QQMessage([QQMessageSegment.file_image(img) for img in imgs])
        await matcher.finish(msg)
    
async def remove_ban_user(arg: Message|QQMessage):
    ''''解黑'''
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    try:
        del ban_tmp[arg.extract_plain_text()]
        banpath.write_text(json.dumps(ban_tmp))
    except Exception:
        await matcher.finish("失败")
    
    await matcher.finish("成功")
    
async def add_white_list(arg: Message|QQMessage):
    '''OneBot适配器加白 传入消息则消息为目标群号，传str则它为群号'''
    matcher: Matcher = current_matcher.get()
    ban_tmp = json.loads(banpath.read_text("utf-8"))
    id = ""
    if isinstance(arg, QQMessage):
        id,this_type = await get_id_from_guild_group(event=current_event.get()) # type: ignore
    else:
        this_type = "group"
    plus = False
    if arg.extract_plain_text().startswith("plus"):
        plus = True
        arg = Message(arg.extract_plain_text()[4:])
    if " " in arg.extract_plain_text():
        sp = arg.extract_plain_text().split(" ")
        id = sp[0]
        this_type = sp[1]
        if this_type not in ["group","private","群","个人"]:
            await matcher.finish("白名单类型错误了，仅支持 群 / 个人，不输入默认为群")
        this_type = "group" if this_type == "群" else "private"
    else:
        id = arg.extract_plain_text()
        
    if id in ban_tmp:
        await matcher.finish("对方在黑名单中哦，真的要继续吗？")
        
    await matcher.finish(await add_white(id, this_type, plus))
    
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
                await matcher.finish("白名单类型错误了，仅支持 群 / 个人，不输入默认为群")
            this_type = "group" if this_type == "群" else "private"
        else:
            id = arg.extract_plain_text()
        
    await matcher.finish(await del_white(id, this_type))
    
async def white_list(chatbot: chatgpt):
    '''获取白名单列表'''
    matcher: Matcher = current_matcher.get()
    white_tmp = json.loads(whitepath.read_text("utf-8"))
    cdk_list = json.loads(cdklistpath.read_text())
    cdk_source = json.loads(cdksource.read_text())
    combined_dict = {cdk_list[key]: cdk_source[key] for key in cdk_list if key in cdk_source}
    plus_status_tmp = json.loads(plusstatus.read_text())
    all_white_ids = {id for ids in white_tmp.values() for id in ids}
    msg = "\n|类型|账号|plus|\n|:------:|:------:|:------:|\n"
    for x in white_tmp:
        for id in white_tmp[x]:
            if id in combined_dict:
                if id in plus_status_tmp:
                    msg += f"|{x}|{str(id)}({combined_dict[id]})|plus|\n"
                else:
                    msg += f"|{x}|{str(id)}({combined_dict[id]})| |\n"
            else:
                if id in plus_status_tmp:
                    msg += f"|{x}|{str(id)}|plus|\n"
                else:
                    msg += f"|{x}|{str(id)}| |\n"
    for id in plus_status_tmp:
        if id not in all_white_ids and id != 'status':
            msg += f"|unknown|{str(id)}|only plus|\n"
    event = current_event.get()
    white_list_img = await md_to_pic(msg, width=650)
    white_list_img = awa
    text = f"当前 3.5 白名单状态：{'开启' if config_gpt.gpt_white_list_mode else '关闭'}\n当前 plus 白名单状态：{'开启' if config_gpt.gptplus_white_list_mode else '关闭'}\n注意：两种白名单模式独立生效"
    if isinstance(event,QQGroupAtMessageCreateEvent):
        #qq适配器的QQ群，暂不支持直接发送图片 (x 现在能发了)   
        await matcher.finish(QQMessageSegment.text(text) + QQMessageSegment.file_image(b64encode(white_list_img).decode('utf-8'))) # type: ignore
    elif isinstance(event,MessageEvent):
        await matcher.finish(MessageSegment.text(text) + MessageSegment.image(file=white_list_img))
    else:
        await matcher.finish(QQMessageSegment.text(text) + QQMessageSegment.file_image(white_list_img))
        
async def md_status(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage):
    '''md开关'''
    md_status_tmp = json.loads(mdstatus.read_text())
    matcher: Matcher = current_matcher.get()
    if isinstance(event,PrivateMessageEvent):
        # 私聊协议bot
        if arg.extract_plain_text().strip() == "开启":
            if event.get_user_id() in md_status_tmp["private"]:
                await matcher.finish("已经开启过了")
            else:
                md_status_tmp["private"].append(event.get_user_id())
        elif arg.extract_plain_text().strip() == "关闭":
            if event.get_user_id() not in md_status_tmp["private"]:
                await matcher.finish("已经关闭过了")
            else:
                md_status_tmp["private"].remove(event.get_user_id())
        else:
            await matcher.finish("指令不正确，请输入 md状态开启 或 md状态关闭")
            
    else:
        if isinstance(event,GroupMessageEvent):
            # 群协议bot，仅管理员
            if event.sender.role != "owner" and event.sender.role != "admin":
                await matcher.finish("在群内仅群管理员可修改md状态")
        id,value = await get_id_from_all(event)
        if arg.extract_plain_text().strip() == "开启":
            if id in md_status_tmp["group"]:
                await matcher.finish("已经开启过了")
            else:
                md_status_tmp["group"].append(id)
        elif arg.extract_plain_text().strip() == "关闭":
            if id not in md_status_tmp["group"]:
                await matcher.finish("已经关闭过了")
            else:
                md_status_tmp["group"].remove(id)
        else:
            await matcher.finish("指令不正确，输入 md状态开启 或 md状态关闭")

        
    mdstatus.write_text(json.dumps(md_status_tmp))
    await matcher.finish("状态修改成功")
    
    
async def random_cdk_api(arg: QQMessage):
    '''生成用户可用的cdk'''
    matcher: Matcher = current_matcher.get()
    if not arg.extract_plain_text():
        logger.debug("cdk需要申请人信息")
        await matcher.finish("cdk需要申请人信息")
    key = uuid.uuid4().hex
    # cdk_list 存储cdk对应QQ适配器群聊ID
    cdk_list = json.loads(cdklistpath.read_text())
    # cdk_source 存储cdk对应申请人信息
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
    await add_white_list(QQMessage(id))
    
async def add_plus(arg: Message|QQMessage):
    '''超管添加用户plus'''
    plus_status_tmp = json.loads(plusstatus.read_text())
    matcher: Matcher = current_matcher.get()
    if arg.extract_plain_text() in plus_status_tmp:
        await matcher.finish(f"{arg.extract_plain_text()} 已经添加过了")
    plus_status_tmp[arg.extract_plain_text()] = all_models_values()[0]
    plusstatus.write_text(json.dumps(plus_status_tmp))
    await matcher.finish(f"{arg.extract_plain_text()} plus 添加完成")
    
async def del_plus(arg: Message|QQMessage):
    '''超管删除用户plus'''
    plus_status_tmp = json.loads(plusstatus.read_text())
    matcher: Matcher = current_matcher.get()
    if arg.extract_plain_text() not in plus_status_tmp:
        await matcher.finish(f"{arg.extract_plain_text()} 并不在plus白名单内")
    del plus_status_tmp[arg.extract_plain_text()]
    plusstatus.write_text(json.dumps(plus_status_tmp))
    await matcher.finish(f"{arg.extract_plain_text()} plus 删除完成")
    
async def plus_change(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage):
    '''plus用户切换模型'''
    plus_status_tmp = json.loads(plusstatus.read_text())
    matcher: Matcher = current_matcher.get()
    if not plus_status_tmp['status']:
        await matcher.finish('超管已关闭plus使用')
    id,value = await get_id_from_all(event)
    data = MsgData()
    data = get_c_id(id,data,value)
    group_conversations = json.loads(group_conversations_path.read_text())
    private_conversations = json.loads(private_conversations_path.read_text())

    if isinstance(event, PrivateMessageEvent):
        if id not in private_conversations:
            await matcher.finish("当前会话未记录plus账号信息，请重新 plus初始化 后再试")
        for session in config_gpt.gpt_session:
            for conversation in private_conversations[id]:
                if conversation["conversation_id"] == data.conversation_id:
                    if session["email"] == conversation['from_email']:
                        if not session["gptplus"]:
                            await matcher.finish(f"当前会话所属账号信息{session["email"]} 不是标注的plus账号，请重新 plus初始化 切换账号后再试")
    else:
        if id not in group_conversations:
            await matcher.finish("当前会话未记录plus账号信息，请重新 plus初始化 后再试")
        for session in config_gpt.gpt_session:
            for conversation in group_conversations[id]:
                if conversation["conversation_id"] == data.conversation_id:
                    if session["email"] == conversation['from_email']:
                        if not session["gptplus"]:
                            await matcher.finish(f"当前会话所属账号信息{session["email"]} 不是标注的plus账号，请重新 plus初始化 切换账号后再试")

    if arg.extract_plain_text() in all_models_keys(True):
        plus_status_tmp[id] = get_model_by_key(arg.extract_plain_text(), True)
    else:
        await matcher.finish(f"请输入正确的模型名：{' '.join(all_models_keys(True))}")

    plusstatus.write_text(json.dumps(plus_status_tmp))
    await matcher.finish(f"plus状态变更为 {arg.extract_plain_text()}")

async def conversations_list(chatbot: chatgpt,event: MessageEvent|QQMessageEvent):
    matcher: Matcher = current_matcher.get()
    id,value = await get_id_from_all(event)

    group_conversations = json.loads(group_conversations_path.read_text())
    private_conversations = json.loads(private_conversations_path.read_text())

    if isinstance(event, PrivateMessageEvent):
        if id not in private_conversations:
            await matcher.finish("当前会话未记录，将在下一次初始化后才开始记录")
        c_list = private_conversations[id]
    else:
        if id not in group_conversations:
            await matcher.finish("当前会话未记录，将在下一次初始化后才开始记录")
        c_list = group_conversations[id]
    all_list = "\n|序号|账号|标题|id|\n|:------:|:------:|:------:|:------:|\n"
    
    all_list += ''.join([f"|{str(i+1)}|{x['from_email']}|{x['conversation_name']}|{x['conversation_id']}|\n" for i,x in enumerate(c_list)])
    pic = await md_to_pic(all_list)
    # pic = await chatbot.md2img(all_list)
    if isinstance(event,QQGroupAtMessageCreateEvent):
        #qq适配器的QQ群，暂不支持直接发送图片 (x 现在能发了)   
        await matcher.finish(QQMessageSegment.file_image(b64encode(pic).decode('utf-8'))) # type: ignore
    else:
        await matcher.finish(MessageSegment.image(file=pic))

async def conversation_change(event: MessageEvent|QQMessageEvent,arg: Message|QQMessage):
    matcher: Matcher = current_matcher.get()
    try:
        num = int(arg.extract_plain_text())
        if num > 30 or num < 0:
            raise IndexError
    except ValueError:
        await matcher.finish("切换会话请输入对应序号(1-30)")
    except IndexError:
        await matcher.finish("切换会话请输入对应序号,仅支持 1-30")
    except Exception as e:
        await matcher.finish(f"切换会话 参数错误：{e}，仅支持 1-30")

    id,value = await get_id_from_all(event)

    group_conversations = json.loads(group_conversations_path.read_text())
    private_conversations = json.loads(private_conversations_path.read_text())

    data = MsgData()
    if isinstance(event, PrivateMessageEvent):
        if id not in private_conversations:
            await matcher.finish("当前会话未记录，将在下一次初始化后才开始记录")
        data.conversation_id = private_conversations[id][num-1]["conversation_id"]
        data.title = private_conversations[id][num-1]["conversation_name"]
    else:
        if id not in group_conversations:
            await matcher.finish("当前会话未记录，将在下一次初始化后才开始记录")
        data.conversation_id = group_conversations[id][num-1]["conversation_id"]
        data.title = group_conversations[id][num-1]["conversation_name"]

    set_c_id(id,data,value)
    logger.info(f"id:{id} 切换会话为 {data.title} {data.conversation_id}")
    await matcher.finish(f"切换会话 {data.title} {data.conversation_id} 完成")
        

async def plus_all_status(arg: Message|QQMessage):
    '''超管全局plus状态变更'''
    plus_status_tmp = json.loads(plusstatus.read_text())
    matcher: Matcher = current_matcher.get()
    if arg.extract_plain_text() == '开启':
        if plus_status_tmp['status'] == True:
            await matcher.finish("已经开启过了")
        plus_status_tmp['status'] = True
    elif arg.extract_plain_text() == '关闭':
        if plus_status_tmp['status'] == False:
            await matcher.finish("已经关闭过了")
        plus_status_tmp['status'] = False
    else:
        await matcher.finish("仅支持 开启/关闭")
    plusstatus.write_text(json.dumps(plus_status_tmp))
    await matcher.finish(f"全局plus状态 {arg.extract_plain_text()} 完成")
    
    
def replace_dot_in_domain(text: str):
    '''替换url过检测'''
    # 较为完整的顶级域名列表（截至目前）
    tlds = [
        "com", "org", "net", "edu", "gov", "mil", "int", "info", "biz", "name", "museum", "coop", "aero", "pro", "jobs", "mobi",
        "travel", "xxx", "asia", "cat", "tel", "post", "ac", "ad", "ae", "af", "ag", "ai", "al", "am", "an", "ao", "aq", "ar",
        "as", "at", "au", "aw", "ax", "az", "ba", "bb", "bd", "be", "bf", "bg", "bh", "bi", "bj", "bm", "bn", "bo", "br", "bs",
        "bt", "bv", "bw", "by", "bz", "ca", "cc", "cd", "cf", "cg", "ch", "ci", "ck", "cl", "cm", "cn", "co", "cr", "cu", "cv",
        "cw", "cx", "cy", "cz", "de", "dj", "dk", "dm", "do", "dz", "ec", "ee", "eg", "er", "es", "et", "eu", "fi", "fj", "fk",
        "fm", "fo", "fr", "ga", "gb", "gd", "ge", "gf", "gg", "gh", "gi", "gl", "gm", "gn", "gp", "gq", "gr", "gs", "gt", "gu",
        "gw", "gy", "hk", "hm", "hn", "hr", "ht", "hu", "id", "ie", "il", "im", "in", "io", "iq", "ir", "is", "it", "je", "jm",
        "jo", "jp", "ke", "kg", "kh", "ki", "km", "kn", "kp", "kr", "kw", "ky", "kz", "la", "lb", "lc", "li", "lk", "lr", "ls",
        "lt", "lu", "lv", "ly", "ma", "mc", "md", "me", "mg", "mh", "mk", "ml", "mm", "mn", "mo", "mp", "mq", "mr", "ms", "mt",
        "mu", "mv", "mw", "mx", "my", "mz", "na", "nc", "ne", "nf", "ng", "ni", "nl", "no", "np", "nr", "nu", "nz", "om", "pa",
        "pe", "pf", "pg", "ph", "pk", "pl", "pm", "pn", "pr", "ps", "pt", "pw", "py", "qa", "re", "ro", "rs", "ru", "rw", "sa",
        "sb", "sc", "sd", "se", "sg", "sh", "si", "sj", "sk", "sl", "sm", "sn", "so", "sr", "ss", "st", "su", "sv", "sx", "sy",
        "sz", "tc", "td", "tf", "tg", "th", "tj", "tk", "tl", "tm", "tn", "to", "tp", "tr", "tt", "tv", "tw", "tz", "ua", "ug",
        "uk", "us", "uy", "uz", "va", "vc", "ve", "vg", "vi", "vn", "vu", "wf", "ws", "ye", "yt", "za", "zm", "zw", "academy",
        "accountants", "actor", "adult", "aero", "agency", "airforce", "apartments", "app", "army", "associates", "attorney",
        "auction", "audio", "autos", "band", "bar", "bargains", "beer", "best", "bet", "bid", "bike", "bingo", "bio", "biz",
        "black", "blog", "blue", "bot", "boutique", "build", "builders", "business", "buzz", "cab", "cafe", "camera", "camp", "capital",
        "cards", "care", "career", "careers", "cash", "casino", "catering", "center", "charity", "chat", "cheap", "christmas",
        "church", "city", "claims", "cleaning", "clinic", "clothing", "cloud", "club", "coach", "codes", "coffee", "college",
        "community", "company", "computer", "condos", "construction", "consulting", "contractors", "cooking", "cool", "coop",
        "country", "coupons", "credit", "creditcard", "cricket", "cruises", "dance", "dating", "day", "deals", "degree",
        "delivery", "democrat", "dental", "dentist", "desi", "design", "diamonds", "digital", "direct", "directory", "discount",
        "dog", "domains", "education", "email", "energy", "engineer", "engineering", "enterprises", "equipment", "estate",
        "events", "exchange", "expert", "exposed", "express", "fail", "faith", "family", "fans", "farm", "fashion", "film",
        "finance", "financial", "fish", "fishing", "fitness", "flights", "florist", "flowers", "football", "forsale", "foundation",
        "fun", "fund", "furniture", "futbol", "fyi", "gallery", "games", "gifts", "gives", "glass", "gmbh", "gold", "golf",
        "graphics", "gratis", "green", "gripe", "group", "guide", "guru", "health", "healthcare", "help", "here", "hiphop",
        "hockey", "holdings", "holiday", "home", "homes", "horse", "hospital", "host", "house", "how", "industries", "ink",
        "institute", "insure", "international", "investments", "jewelry", "jobs", "kitchen", "land", "lawyer", "lease",
        "legal", "life", "lighting", "limited", "limo", "link", "live", "loan", "loans", "lol", "love", "ltd", "luxe", "luxury",
        "management", "market", "marketing", "mba", "media", "memorial", "moda", "money", "mortgage", "movie", "museum",
        "name", "navy", "network", "news", "ninja", "now", "online", "ooo", "page", "partners", "parts", "party", "pet",
        "photo", "photography", "photos", "pics", "pictures", "pink", "pizza", "place", "plumbing", "plus", "poker", "press",
        "productions", "properties", "property", "pub", "recipes", "red", "rehab", "reise", "reviews", "rip", "rocks", "run",
        "sale", "salon", "school", "schule", "services", "shoes", "show", "singles", "site", "soccer", "social", "software",
        "solar", "solutions", "space", "studio", "style", "sucks", "supplies", "supply", "support", "surgery", "systems",
        "tattoo", "tax", "taxi", "team", "tech", "technology", "tennis", "theater", "tips", "tires", "today", "tools", "top",
        "tours", "town", "toys", "trade", "training", "travel", "university", "vacations", "vet", "viajes", "video", "villas",
        "vin", "vision", "vodka", "voyage", "watch", "webcam", "website", "wedding", "wiki", "win", "wine", "work", "works",
        "world", "wtf", "zone"
    ]

    # 将顶级域名列表转换为正则表达式
    tlds_pattern = '|'.join(tlds)
    # 正则表达式匹配网址，包括不含 http/https 前缀的情况
    url_pattern = re.compile(
        fr'\b((?:https?://)?(?:[a-zA-Z0-9-]+\.)+(?:{tlds_pattern})(?:/[^\s]*)?)\b'
    )

    def replace_dot(match):
        return match.group(0).replace('.', '。')
    # 使用正则表达式进行替换
    return url_pattern.sub(replace_dot, text)


async def init_personal_api(chatbot: chatgpt,id: str,personal_name: str,type_from: str):
    person_type = json.loads(personpath.read_text("utf8"))
    if personal_name not in person_type:
        logger.warning(f"默认初始化人格名: {personal_name} 不存在")
        return
    data = MsgData()
    if type_from == "QQguild":
        data = get_c_id(id=id,data=data,c_type='group')
        if data.conversation_id == 'pass':
            logger.info(f"默认人设初始化类型：{type_from},id：{id},检测到疑似重复提示消息，不进行初始化")
            return
        data_tmp = MsgData(conversation_id='pass')
        set_c_id(id,data_tmp,'group')
    else:
        data = get_c_id(id=id,data=data,c_type='group' if 'group' in type_from else 'private')
    if data.conversation_id:
        logger.info(f"默认人设初始化类型：{type_from},id：{id},存在默认会话id：{data.conversation_id},不进行新的初始化")
        return
    data.msg_send = personal_name
    data = await chatbot.init_personality(data)
    
    if not data.msg_recv:
        logger.warning( f"默认人设初始化失败，类型：{type_from},id：{id},错误为：\n{data.error_info}")
    if 'group' in type_from or 'guild' in type_from:
        set_c_id(id,data,'group')
    else: 
        set_c_id(id,data,'private')
