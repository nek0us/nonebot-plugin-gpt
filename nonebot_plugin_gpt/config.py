from pydantic import BaseModel, validator
from typing import List, Optional
from nonebot.log import logger
from nonebot import get_driver,get_plugin_config

from .source import ban_str_path

class Config(BaseModel):
    gpt_proxy: Optional[str] = None
    arkose_status: bool = False
    gpt_session: Optional[List[dict]]|str = []
    group_chat: bool = True
    gpt_chat_start: list = []
    gpt_chat_start_in_msg: bool = False 
    begin_sleep_time: bool = False
    gpt_chat_priority: int = 90
    gpt_command_priority: int = 19
    gpt_white_list_mode: bool = True
    gptplus_white_list_mode: bool = True
    gpt_replay_to_replay: bool = False
    gpt_ban_str: Optional[List[str]]|str = []
    gpt_manage_ids: list = []
    gpt_lgr_markdown: bool = False
    gpt_httpx: bool = False
    gpt_url_replace: bool = False
    gpt_auto_init_group: bool = False
    gpt_auto_init_friend: bool = False
    gpt_init_group_pernal_name: Optional[str] = None
    gpt_init_friend_pernal_name: Optional[str] = None
    gpt_save_screen: bool = False
    
    @validator("gpt_manage_ids", always=True, pre=True)
    def check_gpt_manage_ids(cls,v):
        if isinstance(v,list):
            if v != []:
                logger.success(f"已开启 官方管理群 gpt_manage_ids {v}")
            else:
                logger.warning("gpt_manage_ids 未配置")
            return v    
        else:
            logger.warning("gpt_manage_ids 配置错误")
        
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

        
    @validator("arkose_status", always=True, pre=True)
    def check_arkose_status(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已应用 arkose_status 验证配置")
            else:
                logger.success("已关闭 arkose_status 验证配置")
            return v
        
        
    @validator("group_chat", always=True, pre=True)
    def check_group_chat(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 group_chat 多人识别配置")
            else:
                logger.success("已关闭 group_chat 多人识别配置")
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
                logger.success("已开启 gpt_chat_start_in_msg 聊天前缀加入消息")
            else:
                logger.success("已关闭 gpt_chat_start_in_msg 聊天前缀加入消息")
            return v    
            
    @validator("begin_sleep_time", always=True, pre=True)
    def check_begin_sleep_time(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 随机延迟登录")
            else:
                logger.success("已关闭 随机延迟登录")
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
                    logger.warning("账号信息数量异常，请检查")
                return v 
        except Exception:
            logger.warning("未检测到符合条件的账号信息")

    @validator("gpt_white_list_mode", always=True, pre=True)
    def check_gpt_white_list_mode(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_white_list_mode 白名单模式")
            else:
                logger.success("已关闭 gpt_white_list_mode 白名单模式")
            return v    

    @validator("gptplus_white_list_mode", always=True, pre=True)
    def check_gptplus_white_list_mode(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gptplus_white_list_mode 白名单模式")
            else:
                logger.success("已关闭 gptplus_white_list_mode 白名单模式")
            return v  
                
    @validator("gpt_replay_to_replay", always=True, pre=True)
    def check_gpt_replay_to_replay(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_replay_to_replay 回复 回复消息")
            else:
                logger.success("已关闭 gpt_replay_to_replay 回复 回复消息")
            return v      
        
    @validator("gpt_ban_str", always=True, pre=True)
    def check_gpt_ban_str(cls,v):
        try:
            ban_str = eval(v)
            if isinstance(ban_str,list):
                v = ban_str
                if v:
                    ban_str_path.write_text('\n'.join(v))
                    logger.success("已应用 gpt_ban_str 屏蔽词列表")
                else:
                    logger.warning("未配置 gpt 屏蔽词")
                return v 
            logger.warning("未配置 gpt 屏蔽词")
        except Exception:
            logger.warning("未配置 gpt 屏蔽词")

    @validator("gpt_lgr_markdown", always=True, pre=True)
    def check_gpt_lgr_markdown(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_lgr_markdown 拉格兰MarkDown转换")
            else:
                logger.success("已关闭 gpt_lgr_markdown 拉格兰MarkDown转换")
            return v               

    @validator("gpt_httpx", always=True, pre=True)
    def check_gpt_httpx(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_httpx httpx使用")
            else:
                logger.success("已关闭 gpt_httpx httpx使用")
            return v
            
    @validator("gpt_url_replace", always=True, pre=True)
    def check_gpt_url_replace(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_url_replace QQ适配器url输出检测替换")
            else:
                logger.success("已关闭 gpt_url_replace QQ适配器url输出检测替换")
            return v     
            
    @validator("gpt_auto_init_group", always=True, pre=True)
    def check_gpt_auto_init_group(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_auto_init_group 入群默认初始化人设")
            else:
                logger.success("已关闭 gpt_auto_init_group 入群默认初始化人设")
            return v  
            
    @validator("gpt_auto_init_friend", always=True, pre=True)
    def check_gpt_auto_init_friend(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_auto_init_friend 好友默认初始化人设")
            else:
                logger.success("已关闭 gpt_auto_init_friend 好友默认初始化人设")
            return v  
        
    @validator("gpt_init_group_pernal_name")
    def check_gpt_init_group_pernal_name(cls,v):
        if isinstance(v,str):
            logger.success(f"已应用 gpt_init_group_pernal_name 入群初始化默认人设名：{v}")
            return v
        
    @validator("gpt_init_friend_pernal_name")
    def check_gpt_init_friend_pernal_name(cls,v):
        if isinstance(v,str):
            logger.success(f"已应用 gpt_init_friend_pernal_name 好友初始化默认人设名：{v}")
            return v 
        
    @validator("gpt_save_screen", always=True, pre=True)
    def check_gpt_save_screen(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_save_screen 消息与刷新错误截图保存")
            else:
                logger.success("已关闭 gpt_save_screen 消息与刷新错误截图保存")
            return v  
                                                     
config_gpt = get_plugin_config(Config)
config_nb = get_driver().config