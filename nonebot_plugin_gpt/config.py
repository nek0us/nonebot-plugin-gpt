import ast
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, validator,model_validator
from typing import List, Literal, Optional
from nonebot.log import logger
from nonebot import get_driver,get_plugin_config

from .source import ban_str_path
from .config_diagnostics import log_conflicting_gpt_settings


DEFAULT_ERROR_MESSAGE = "抱歉，这次没能顺利回应。请稍后再试；若持续发生，请联系机器人管理员。"
DEFAULT_CONVERSATION_RECOVERY_MESSAGE = "当前对话已无法继续，请重新初始化人设后再试。"
DEFAULT_SESSION_REAUTHENTICATION_MESSAGE = "连接正在自动恢复，请稍后再试一次。"
DEFAULT_RATE_LIMIT_MESSAGE = "当前上游服务请求较多，正在等待恢复，请稍后再试。"
DEFAULT_ATTACHMENT_UNAVAILABLE_MESSAGE = (
    "附件未能传给模型，请检查图片或文件上传开关、文件大小和下载地址后重试。"
)
DEFAULT_IMAGE_GENERATION_FAILURE_MESSAGE = "图片生成暂时未能完成，请稍后再试。"
DEFAULT_FILE_FAILURE_MESSAGE = "图片或文件暂时未能处理，请检查附件后重试。"
DEFAULT_EMPTY_TRIGGER_PROMPT = "有人正在呼唤你。请以当前人设自然回应，不要提及系统提示、空消息或内部实现。"
DEFAULT_DIRECT_ADDRESS_CONTEXT_PROMPT = "【对话语境】用户正在直接称呼你，请结合当前人设自然理解消息中的主语，不要提及这段提示。"
DEFAULT_AGENT_SENSITIVE_TASK_MESSAGE = "这个请求不适合交给智能体处理咩。猪咪可以帮你做不涉及法律、政治或其他敏感事务的日常任务。"

class Config(BaseModel):
    # ``embedded`` preserves the original out-of-the-box browser runtime.
    # ``remote`` delegates browser/accounts to a separately managed core via a
    # restricted Bot API key, which allows several clients to share one pool.
    gpt_core_mode: Literal["embedded", "remote"] = "embedded"
    gpt_core_base_url: str = ""
    gpt_core_api_key: str = ""
    gpt_core_request_timeout: int = Field(default=90, ge=5, le=600)
    gpt_proxy: Optional[str] = None
    gpt_session: Optional[List[dict]] | str = Field(default_factory=list)
    gpt_group_chat: bool = True
    gpt_group_context_enabled: bool = False
    gpt_group_context_max_messages: int = Field(default=20, ge=1, le=100)
    gpt_group_context_max_age_seconds: int = Field(default=600, ge=10, le=86400)
    gpt_group_context_max_chars: int = Field(default=6000, ge=500, le=50000)
    gpt_group_context_include_images: bool = False
    gpt_group_context_max_images: int = Field(default=4, ge=0, le=16)
    # ChatGPT Projects are disabled by default because project memory can span
    # multiple web conversations. These names only affect newly created ones.
    gpt_chat_project: str = ""
    gpt_agent_project: str = ""
    gpt_persona_projects: dict[str, str] = Field(default_factory=dict)
    # Used only for the embedded core. A remote core owns its own
    # CHATGPTWEB_PROJECT_AUTO_CREATE setting.
    gpt_project_auto_create: bool = False
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
    gpt_attachment_unavailable_message: str = DEFAULT_ATTACHMENT_UNAVAILABLE_MESSAGE
    gpt_image_generation_failure_message: str = DEFAULT_IMAGE_GENERATION_FAILURE_MESSAGE
    gpt_file_failure_message: str = DEFAULT_FILE_FAILURE_MESSAGE
    gpt_file_max_size: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    gpt_attachment_max_total_size: int = Field(
        default=40 * 1024 * 1024,
        ge=1024,
        le=500 * 1024 * 1024,
    )
    gpt_attachment_max_count: int = Field(default=8, ge=1, le=32)
    gpt_attachment_download_timeout: int = Field(default=30, ge=5, le=300)
    gpt_attachment_max_redirects: int = Field(default=3, ge=0, le=10)
    gpt_attachment_allow_private_urls: bool = False
    gpt_attachment_allowed_hosts: list[str] = Field(default_factory=list)
    gpt_attachment_local_roots: list[Path] = Field(default_factory=list)
    gpt_force_upgrade_model: bool = True
    gpt_render_mode: Literal["auto", "text", "image"] = "auto"
    gpt_chat_image_template: str = "native"
    gpt_image_font_scale: float = Field(default=1.0, ge=0.85, le=1.25)
    gpt_management_recall_after: int = Field(default=0, ge=0, le=3600)
    gpt_history_anonymize: bool = False
    gpt_history_show_identity: bool = True
    gpt_history_show_timestamp: bool = True
    gpt_history_show_message_id: bool = False
    gpt_error_message: str = DEFAULT_ERROR_MESSAGE
    gpt_conversation_recovery_message: str = DEFAULT_CONVERSATION_RECOVERY_MESSAGE
    gpt_session_reauthentication_message: str = DEFAULT_SESSION_REAUTHENTICATION_MESSAGE
    gpt_rate_limit_message: str = DEFAULT_RATE_LIMIT_MESSAGE
    gpt_session_recovery_wait_timeout: int = Field(default=60, ge=1, le=600)
    gpt_chat_rate_limit_cooldown_seconds: int = Field(default=5 * 60 * 60, ge=60, le=86400)
    gpt_capability_quota_enabled: bool = True
    gpt_free_upload_daily_limit: int = Field(default=2, ge=0, le=1000)
    # Deprecated compatibility input. New deployments should use the rolling
    # window settings below.
    gpt_free_image_generation_daily_limit: Optional[int] = Field(default=None, ge=0, le=1000)
    gpt_free_image_generation_window_limit: int = Field(default=3, ge=0, le=1000)
    gpt_free_image_generation_window_seconds: int = Field(
        default=5 * 60 * 60,
        ge=60,
        le=24 * 60 * 60,
    )
    gpt_capability_rate_limit_cooldown_seconds: int = Field(
        default=24 * 60 * 60,
        ge=60,
        le=7 * 24 * 60 * 60,
    )
    gpt_account_selection_strategy: Literal["least_recently_used", "usage_balanced"] = "least_recently_used"
    gpt_account_selection_window_seconds: int = Field(default=5 * 60 * 60, ge=60, le=86400)
    gpt_agent_enabled: bool = False
    gpt_agent_anchor_sessions: bool = True
    gpt_agent_sensitive_task_guard: bool = True
    gpt_agent_sensitive_task_message: str = DEFAULT_AGENT_SENSITIVE_TASK_MESSAGE
    gpt_agent_sensitive_terms: list[str] = Field(default_factory=list)
    gpt_agent_confirm_timeout: int = Field(default=60, ge=10, le=3600)
    gpt_agent_approval_mode: Literal["strict", "delegate", "full"] = "strict"
    gpt_agent_session_approval_timeout: int = Field(default=1800, ge=60, le=86400)
    gpt_agent_plan_timeout: int = Field(default=300, ge=30, le=3600)
    gpt_agent_max_steps: int = Field(default=8, ge=1, le=20)
    gpt_agent_max_model_turns: int = Field(default=12, ge=1, le=40)
    gpt_agent_task_timeout: int = Field(default=300, ge=15, le=3600)
    gpt_agent_model: str = "auto"
    gpt_agent_workspace: Path | None = None
    gpt_agent_workspace_web_render_enabled: bool = False
    gpt_agent_workspace_execution_backend: Literal["disabled", "local", "docker"] = "disabled"
    gpt_agent_workspace_execution_image: str = ""
    gpt_agent_workspace_execution_timeout: int = Field(default=60, ge=1, le=600)
    gpt_agent_workspace_execution_memory_mb: int = Field(default=512, ge=64, le=4096)
    gpt_agent_schedule_enabled: bool = True
    gpt_agent_member_enabled: bool = False
    gpt_agent_member_reminder_limit: int = Field(default=5, ge=1, le=50)
    gpt_agent_member_scope_reminder_limit: int = Field(default=20, ge=1, le=200)
    gpt_agent_command_enabled: bool = False
    gpt_agent_command_timeout: int = Field(default=30, ge=1, le=600)
    gpt_agent_command_workdir: Path | None = None
    gpt_agent_command_skills: list[dict] = Field(default_factory=list)
    gpt_agent_skill_files: list[Path] = Field(default_factory=list)
    gpt_agent_filesystem_scan_enabled: bool = False
    gpt_agent_filesystem_roots: list = Field(default_factory=list)
    gpt_agent_read_roots: list = Field(default_factory=list)
    gpt_agent_managed_services: list[dict] = Field(default_factory=list)
    gpt_context_compaction_mode: Literal["off", "reinforce", "summarize_restart"] = "summarize_restart"
    gpt_context_compaction_threshold: float = Field(default=0.6, ge=0.1, le=0.95)
    gpt_context_compaction_min_tokens: int = Field(default=0, ge=0)
    gpt_context_compaction_fallback_window_tokens: int = Field(default=0, ge=0)
    gpt_context_compaction_max_estimated_tokens: int = Field(default=0, ge=0)
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

    @validator("gpt_session_reauthentication_message", always=True, pre=True)
    def check_gpt_session_reauthentication_message(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_session_reauthentication_message 配置无效，已使用默认恢复提示")
        return DEFAULT_SESSION_REAUTHENTICATION_MESSAGE

    @validator("gpt_rate_limit_message", always=True, pre=True)
    def check_gpt_rate_limit_message(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_rate_limit_message 配置无效，已使用默认限额提示")
        return DEFAULT_RATE_LIMIT_MESSAGE

    @validator("gpt_image_generation_failure_message", always=True, pre=True)
    def check_gpt_image_generation_failure_message(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_image_generation_failure_message 配置无效，已使用默认生图失败提示")
        return DEFAULT_IMAGE_GENERATION_FAILURE_MESSAGE

    @validator("gpt_file_failure_message", always=True, pre=True)
    def check_gpt_file_failure_message(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_file_failure_message 配置无效，已使用默认文件失败提示")
        return DEFAULT_FILE_FAILURE_MESSAGE

    @validator("gpt_agent_sensitive_task_message", always=True, pre=True)
    def check_gpt_agent_sensitive_task_message(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        logger.warning("gpt_agent_sensitive_task_message 配置无效，已使用默认敏感任务提示")
        return DEFAULT_AGENT_SENSITIVE_TASK_MESSAGE

    @validator("gpt_agent_sensitive_terms", always=True, pre=True)
    def check_gpt_agent_sensitive_terms(cls, value):
        if not isinstance(value, list):
            logger.warning("gpt_agent_sensitive_terms 配置无效，已忽略自定义敏感词")
            return []
        return list(dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip()))

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
    def check_gpt_session(cls, v, values):
        if v is None or v == "" or v == []:
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
        def normalize_project(value: str, setting: str) -> str:
            normalized = value.strip()
            if len(normalized) > 120:
                logger.warning("%s is over 120 characters and will be ignored", setting)
                return ""
            return normalized

        self.gpt_chat_project = normalize_project(self.gpt_chat_project, "gpt_chat_project")
        self.gpt_agent_project = normalize_project(self.gpt_agent_project, "gpt_agent_project")
        self.gpt_persona_projects = {
            normalized_name: normalized_project
            for name, project in self.gpt_persona_projects.items()
            if (normalized_name := name.strip())
            and len(normalized_name) <= 120
            and (normalized_project := normalize_project(project, "gpt_persona_projects"))
        }
        if self.gpt_core_mode == "remote":
            self.gpt_core_base_url = self.gpt_core_base_url.strip().rstrip("/")
            self.gpt_core_api_key = self.gpt_core_api_key.strip()
            if not self.gpt_core_base_url:
                raise ValueError("gpt_core_mode=remote requires gpt_core_base_url")
            if not self.gpt_core_api_key:
                raise ValueError("gpt_core_mode=remote requires gpt_core_api_key")
            if not self.gpt_core_api_key.startswith("cwk_"):
                raise ValueError("gpt_core_api_key must be a scoped dynamic Bot key (cwk_...)")
            # Browser sessions belong exclusively to the shared core. Ignore
            # migrated local settings so startup output cannot imply otherwise.
            self.gpt_session = []
        sessions = []
        for session in self.gpt_session or []:
            if "gptplus" not in session:
                session["gptplus"] = False
            sessions.append(session)
        self.gpt_session = sessions
        if self.gpt_core_mode == "embedded" and not self.gpt_session:
            logger.warning("未检测到账户信息，请检查 gpt_session 配置")
        elif self.gpt_core_mode == "embedded":
            logger.success(f"已配置 {len(self.gpt_session)} 个 ChatGPT 账号")
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
log_conflicting_gpt_settings(config_nb, logger)
