import ast
import json

from pydantic import BaseModel, Field, validator,model_validator
from typing import List, Literal, Optional
from nonebot.log import logger
from nonebot import get_driver,get_plugin_config

from .source import ban_str_path

class Config(BaseModel):
    gpt_proxy: Optional[str] = None
    arkose_status: bool = False
    gpt_session: Optional[List[dict]] | str = Field(default_factory=list)
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
    gpt_save_screen: bool = False
    gpt_headless: bool = True
    gpt_local_js: bool = False
    gpt_free_image: bool = False
    gpt_force_upgrade_model: bool = True
    gpt_render_mode: Literal["auto", "text", "image"] = "auto"
    gpt_context_compaction_mode: Literal["off", "reinforce", "summarize_restart"] = "summarize_restart"
    gpt_context_compaction_threshold: float = Field(default=0.6, ge=0.1, le=0.95)
    gpt_context_compaction_min_tokens: int = Field(default=0, ge=0)
    
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
        if v is None or v == "" or v == []:
            logger.warning("未检测到账户信息，请检查 gpt_session 配置")
            return []

        if isinstance(v, list):
            sessions = v
        elif isinstance(v, str):
            try:
                sessions = json.loads(v)
            except json.JSONDecodeError:
                try:
                    # 兼容使用 Python 字面量的旧版 .env 配置。
                    sessions = ast.literal_eval(v)
                except (SyntaxError, ValueError):
                    logger.warning("gpt_session 配置格式错误，应为 JSON 账号列表")
                    return []
        else:
            logger.warning("gpt_session 配置格式错误，应为账号列表")
            return []

        if not isinstance(sessions, list) or not all(isinstance(session, dict) for session in sessions):
            logger.warning("gpt_session 配置格式错误，列表成员应为账号对象")
            return []

        if sessions:
            logger.success(f"已配置 {len(sessions)} 个 ChatGPT 账号")
        else:
            logger.warning("gpt_session 账号列表为空")
        return sessions

        # 以下旧逻辑保留用于兼容历史版本，正常流程会在上方返回。
        try:
            session_user = ast.literal_eval(v)
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

    @model_validator(mode="after")
    def validate_plus(self) -> "Config":
        sessions = []
        for session in self.gpt_session or []:
            if "gptplus" not in session:
                session["gptplus"] = False
            sessions.append(session)
        self.gpt_session = sessions
        return self

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

    @validator("gpt_save_screen", always=True, pre=True)
    def check_gpt_save_screen(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_save_screen 消息与刷新错误截图保存")
            else:
                logger.success("已关闭 gpt_save_screen 消息与刷新错误截图保存")
            return v  
        
    @validator("gpt_headless", always=True, pre=True)
    def check_gpt_headless(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_headless 模式")
            else:
                logger.success("已关闭 gpt_headless 模式")
            return v  
        
    
    @validator("gpt_local_js", always=True, pre=True)
    def check_gpt_local_js(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_local_js 加载本地js")
            else:
                logger.success("已开启 gpt_local_js 联网获取js")
            return v  
        
    
    @validator("gpt_free_image", always=True, pre=True)
    def check_gpt_free_image(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_free_image 免费账户上传图片，额度很低请注意")
            else:
                logger.success("已关闭 gpt_free_image 免费账户上传图片")
            return v  
        
    
    @validator("gpt_force_upgrade_model", always=True, pre=True)
    def check_force_upgrade_model(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_force_upgrade_model 强制会话升级基础模型")
            else:
                logger.success("已关闭 gpt_force_upgrade_model 强制会话升级基础模型")
            return v  
                                                     
config_gpt = get_plugin_config(Config)
config_nb = get_driver().config
