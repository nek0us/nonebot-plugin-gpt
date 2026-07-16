import ast
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, validator,model_validator
from typing import List, Literal, Optional
from nonebot.log import logger
from nonebot import get_driver,get_plugin_config

from .source import ban_str_path


DEFAULT_ERROR_MESSAGE = "抱歉，这次没能顺利回应。请稍后再试；若持续发生，请联系机器人管理员。"
DEFAULT_CONVERSATION_RECOVERY_MESSAGE = "当前对话已无法继续，请重新初始化人设后再试。"
DEFAULT_EMPTY_TRIGGER_PROMPT = "有人正在呼唤你。请以当前人设自然回应，不要提及系统提示、空消息或内部实现。"
DEFAULT_DIRECT_ADDRESS_CONTEXT_PROMPT = "【对话语境】用户正在直接称呼你，请结合当前人设自然理解消息中的主语，不要提及这段提示。"

class Config(BaseModel):
    gpt_proxy: Optional[str] = None
    gpt_session: Optional[List[dict]] | str = Field(default_factory=list)
    gpt_group_chat: bool = True
    gpt_chat_start: list = []
    gpt_chat_start_in_msg: bool = False 
    gpt_empty_trigger_prompt: str = DEFAULT_EMPTY_TRIGGER_PROMPT
    gpt_direct_address_context_enabled: bool = False
    gpt_direct_address_context_prompt: str = DEFAULT_DIRECT_ADDRESS_CONTEXT_PROMPT
    gpt_begin_sleep_time: bool = False
    gpt_chat_priority: int = 90
    gpt_command_priority: int = 19
    gpt_white_list_mode: bool = True
    gpt_plus_white_list_mode: bool = True
    gpt_replay_to_replay: bool = False
    gpt_ban_str: Optional[List[str]]|str = []
    gpt_manage_ids: list = []
    gpt_save_screen: bool = False
    gpt_headless: bool = True
    gpt_local_js: bool = False
    gpt_control_host: str = "127.0.0.1"
    gpt_control_port: Optional[int] = Field(default=None, ge=0, le=65535)
    gpt_control_api_key: Optional[str] = None
    gpt_free_image: bool = False
    gpt_file_upload: bool = False
    gpt_file_max_size: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    gpt_force_upgrade_model: bool = True
    gpt_render_mode: Literal["auto", "text", "image"] = "auto"
    gpt_chat_image_template: str = "native"
    gpt_management_recall_after: int = Field(default=0, ge=0, le=3600)
    gpt_error_message: str = DEFAULT_ERROR_MESSAGE
    gpt_conversation_recovery_message: str = DEFAULT_CONVERSATION_RECOVERY_MESSAGE
    gpt_agent_enabled: bool = False
    gpt_agent_confirm_timeout: int = Field(default=60, ge=10, le=3600)
    gpt_agent_session_approval_timeout: int = Field(default=1800, ge=60, le=86400)
    gpt_agent_plan_timeout: int = Field(default=300, ge=30, le=3600)
    gpt_agent_workspace: Path | None = None
    gpt_agent_managed_services: list[dict] = Field(default_factory=list)
    gpt_context_compaction_mode: Literal["off", "reinforce", "summarize_restart"] = "summarize_restart"
    gpt_context_compaction_threshold: float = Field(default=0.6, ge=0.1, le=0.95)
    gpt_context_compaction_min_tokens: int = Field(default=0, ge=0)
    gpt_auto_init_group: bool = False
    gpt_auto_init_friend: bool = False
    gpt_init_group_persona_name: str = ""
    gpt_init_friend_persona_name: str = ""
    # 保留历史拼写，防止现有部署静默失效。
    gpt_init_group_pernal_name: str = ""
    gpt_init_friend_pernal_name: str = ""

    @validator("gpt_error_message", always=True, pre=True)
    def check_gpt_error_message(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_error_message 配置无效，已使用默认失败提示")
        return DEFAULT_ERROR_MESSAGE

    @validator("gpt_conversation_recovery_message", always=True, pre=True)
    def check_gpt_conversation_recovery_message(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_conversation_recovery_message 配置无效，已使用默认会话恢复提示")
        return DEFAULT_CONVERSATION_RECOVERY_MESSAGE

    @validator("gpt_empty_trigger_prompt", always=True, pre=True)
    def check_gpt_empty_trigger_prompt(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_empty_trigger_prompt 配置无效，已使用默认呼唤提示")
        return DEFAULT_EMPTY_TRIGGER_PROMPT

    @validator("gpt_direct_address_context_prompt", always=True, pre=True)
    def check_gpt_direct_address_context_prompt(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_direct_address_context_prompt 配置无效，已使用默认称呼语境提示")
        return DEFAULT_DIRECT_ADDRESS_CONTEXT_PROMPT

    @validator("gpt_chat_image_template", always=True, pre=True)
    def check_gpt_chat_image_template(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_chat_image_template 配置无效，已使用 native 聊天图片主题")
        return "native"
    
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

        
    @validator("gpt_group_chat", always=True, pre=True)
    def check_group_chat(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_group_chat 多人识别配置")
            else:
                logger.success("已关闭 gpt_group_chat 多人识别配置")
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
            
    @validator("gpt_begin_sleep_time", always=True, pre=True)
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
        if not self.gpt_init_group_persona_name and self.gpt_init_group_pernal_name:
            self.gpt_init_group_persona_name = self.gpt_init_group_pernal_name
            logger.warning(
                "gpt_init_group_pernal_name 为历史拼写，请迁移为 gpt_init_group_persona_name"
            )
        if not self.gpt_init_friend_persona_name and self.gpt_init_friend_pernal_name:
            self.gpt_init_friend_persona_name = self.gpt_init_friend_pernal_name
            logger.warning(
                "gpt_init_friend_pernal_name 为历史拼写，请迁移为 gpt_init_friend_persona_name"
            )
        if self.gpt_auto_init_group and not self.gpt_init_group_persona_name:
            logger.warning("已开启 gpt_auto_init_group，但未配置群聊默认人设")
        if self.gpt_auto_init_friend and not self.gpt_init_friend_persona_name:
            logger.warning("已开启 gpt_auto_init_friend，但未配置私聊默认人设")
        deprecated = {
            "begin_sleep_time": "gpt_begin_sleep_time",
            "gpt_lgr_markdown": "gpt_render_mode",
            "gpt_httpx": "已移除，浏览器桥接已替代该实现",
            "gpt_url_replace": "已移除，统一消息输出已替代该实现",
        }
        for old_name, replacement in deprecated.items():
            if old_name in os.environ:
                logger.warning(f"检测到已废弃配置 {old_name}，请迁移为 {replacement}")
        return self

    @validator("gpt_white_list_mode", always=True, pre=True)
    def check_gpt_white_list_mode(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_white_list_mode 白名单模式")
            else:
                logger.success("已关闭 gpt_white_list_mode 白名单模式")
            return v    

    @validator("gpt_plus_white_list_mode", always=True, pre=True)
    def check_gpt_plus_white_list_mode(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_plus_white_list_mode 白名单模式")
            else:
                logger.success("已关闭 gpt_plus_white_list_mode 白名单模式")
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

    @validator("gpt_file_upload", always=True, pre=True)
    def check_gpt_file_upload(cls,v):
        if isinstance(v,bool):
            if v:
                logger.success("已开启 gpt_file_upload 普通文件上传")
            else:
                logger.success("已关闭 gpt_file_upload 普通文件上传")
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
