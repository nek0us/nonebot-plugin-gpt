from pydantic import BaseModel, validator, root_validator
from typing import List, Optional
from playwright._impl._api_structures import ProxySettings
from nonebot.log import logger
from nonebot import get_driver

from .source import ban_str_path

class Config(BaseModel):
    gpt_proxy: Optional[str] = None
    pywt_proxy: Optional[ProxySettings] = None
    arkose_status: bool = False
    gpt_session: Optional[List[dict]]|str = []
    group_chat: bool = True
    gpt_chat_start: list = []
    gpt_chat_start_in_msg: bool = False 
    begin_sleep_time: bool = False
    gpt_chat_priority: int = 90
    gpt_command_priority: int = 19
    gpt_white_list_mode: bool = True
    gpt_replay_to_replay: bool = False
    gpt_ban_str: Optional[List[str]]|str = []
    gpt_manage_ids: list = []
    gpt_lgr_markdown: bool = False
    gpt_httpx: bool = False
    
    @validator("gpt_manage_ids", always=True, pre=True)
    def check_gpt_manage_ids(cls,v):
        if isinstance(v,list):
            if v != []:
                logger.success(f"已开启 官方管理群 gpt_manage_ids {v}")
            else:
                logger.warning(f"gpt_manage_ids 未配置")
            return v    
        else:
            logger.warning(f"gpt_manage_ids 配置错误")
        
    @validator("gpt_chat_priority", always=True, pre=True)
    def check_gpt_chat_priority(cls,v):
        if isinstance(v,int) and v >= 1:
            logger.success(f"已应用 聊天事件响应优先级 gpt_chat_priority {v}")
            return v
        
    @validator("gpt_command_priority", always=True, pre=True)
    def check_gpt_command_priority(cls,v):
        if isinstance(v,int) and v >= 1:
            logger.success(f"已应用 命令事件响应优先级 gpt_command_priority {v}")
            return v
        
    @validator("gpt_proxy")
    def check_gpt_proxy(cls,v):
        if isinstance(v,str):
            logger.success(f"已应用 gpt_proxy 代理配置：{v}")
            return v
        
    @root_validator(pre=False)
    def set_pywt_proxy(cls, values):
        gpt_proxy = values.get('gpt_proxy')
        values['pywt_proxy'] = {"server": gpt_proxy} if gpt_proxy else None
        return values
        
    @validator("arkose_status", always=True, pre=True)
    def check_arkose_status(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已应用 arkose_status 验证配置")
            else:
                logger.success(f"已关闭 arkose_status 验证配置")
            return v
        
        
    @validator("group_chat", always=True, pre=True)
    def check_group_chat(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已开启 group_chat 多人识别配置")
            else:
                logger.success(f"已关闭 group_chat 多人识别配置")
            return v    
        
    @validator("gpt_chat_start", always=True, pre=True)
    def check_gpt_chat_start(cls,v):
        if isinstance(v,list):
            if v:
                logger.success(f"已配置 gpt_chat_start 聊天前缀 {' '.join(v)}")
            return v      
        
    @validator("gpt_chat_start_in_msg", always=True, pre=True)
    def check_gpt_chat_start_in_msg(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已开启 gpt_chat_start_in_msg 聊天前缀加入消息")
            else:
                logger.success(f"已关闭 gpt_chat_start_in_msg 聊天前缀加入消息")
            return v    
            
    @validator("begin_sleep_time", always=True, pre=True)
    def check_begin_sleep_time(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已开启 随机延迟登录")
            else:
                logger.success(f"已关闭 随机延迟登录")
            return v 
        
    @validator("gpt_session", always=True, pre=True)
    def check_gpt_session(cls,v):
        try:
            session_user = eval(v)
            if isinstance(session_user,list):
                num = len(session_user)
                v = session_user
                if num > 0:
                    logger.success(f"已配置 {str(num)} 个账号信息")
                else:
                    logger.warning(f"账号信息数量异常，请检查")
                return v 
        except:
            logger.warning(f"未检测到符合条件的账号信息")

    @validator("gpt_white_list_mode", always=True, pre=True)
    def check_gpt_white_list_mode(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已开启 gpt_white_list_mode 白名单模式")
            else:
                logger.success(f"已关闭 gpt_white_list_mode 白名单模式")
            return v    
        
    @validator("gpt_replay_to_replay", always=True, pre=True)
    def check_gpt_replay_to_replay(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已开启 gpt_replay_to_replay 回复 回复消息")
            else:
                logger.success(f"已关闭 gpt_replay_to_replay 回复 回复消息")
            return v      
        
    @validator("gpt_ban_str", always=True, pre=True)
    def check_gpt_ban_str(cls,v):
        try:
            ban_str = eval(v)
            if isinstance(ban_str,list):
                v = ban_str
                if v:
                    ban_str_path.write_text('\n'.join(v))
                    logger.success(f"已应用 gpt_ban_str 屏蔽词列表")
                else:
                    logger.warning(f"未配置 gpt 屏蔽词")
                return v 
            logger.warning(f"未配置 gpt 屏蔽词")
        except Exception as e:
            logger.warning(f"未配置 gpt 屏蔽词")

    @validator("gpt_lgr_markdown", always=True, pre=True)
    def check_gpt_lgr_markdown(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已开启 gpt_lgr_markdown 拉格兰MarkDown转换")
            else:
                logger.success(f"已关闭 gpt_lgr_markdown 拉格兰MarkDown转换")
            return v               

    @validator("gpt_httpx", always=True, pre=True)
    def check_gpt_httpx(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success(f"已开启 gpt_httpx httpx使用")
            else:
                logger.success(f"已关闭 gpt_httpx httpx使用")
            return v    
                         
config_gpt = Config.parse_obj(get_driver().config)
config_nb = get_driver().config