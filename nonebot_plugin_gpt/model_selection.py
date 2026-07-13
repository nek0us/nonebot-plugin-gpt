"""兼容现有模型白名单配置的会话模型选择。"""

from __future__ import annotations

import json

from ChatGPTWeb.config import all_free_models_values, all_models_values
from nonebot.adapters import Event



def _upgrade_free_model(model: str) -> str:
    """沿用原有配置：会话被限制时降级到默认基础模型。"""
    free_models = all_free_models_values()
    if model in free_models and model in all_models_values() and model != free_models[0]:
        return free_models[0]
    return model


async def _legacy_identifier(event: Event) -> str:
    """按旧白名单的兼容规则获取会话范围标识。"""
    from .check import get_id_from_all

    identifier, _ = await get_id_from_all(event)  # type: ignore[arg-type]
    return str(identifier)


def _plusstatus_path():
    """延迟访问旧本地存储，避免导入逻辑层时初始化 NoneBot。"""
    from .source import plusstatus

    return plusstatus


def _force_upgrade_model() -> bool:
    """延迟读取插件配置，保持选择器可在无驱动环境中测试。"""
    from .config import config_gpt

    return config_gpt.gpt_force_upgrade_model


async def select_model(event: Event, *, prefer_paid_account: bool = False) -> tuple[str, bool]:
    """从旧 plus 白名单读取模型，同时为新运行时返回账户偏好。"""
    try:
        identifier = await _legacy_identifier(event)
        configured = json.loads(_plusstatus_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return "auto", prefer_paid_account

    model = "auto"
    has_model_override = configured.get("status") and str(identifier) in configured
    if has_model_override:
        model = str(configured[str(identifier)])
        if _force_upgrade_model():
            model = _upgrade_free_model(model)

    inferred_paid = model in all_models_values() and model not in all_free_models_values()
    return model, prefer_paid_account or bool(has_model_override) or inferred_paid
