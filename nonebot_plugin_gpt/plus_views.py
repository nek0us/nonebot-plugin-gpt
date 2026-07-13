"""Plus 权限和逻辑会话模型偏好的纯业务函数。"""

from __future__ import annotations

from collections.abc import MutableMapping


def set_global_paid_enabled(settings: MutableMapping[str, object], value: str) -> str:
    """修改全局 Plus 开关并返回用户可见的结果。"""
    normalized = value.strip().lower()
    if normalized in {"开启", "开", "on", "true", "1"}:
        enabled = True
    elif normalized in {"关闭", "关", "off", "false", "0"}:
        enabled = False
    else:
        raise ValueError("仅支持“开启”或“关闭”。")
    label = "开启" if enabled else "关闭"
    if bool(settings.get("status", True)) == enabled:
        return f"全局 Plus 已经{label}。"
    settings["status"] = enabled
    return f"全局 Plus 已{label}。"


def grant_paid_access(settings: MutableMapping[str, object], identifier: str) -> str:
    """授予一个稳定标识 Plus 使用资格，默认使用自动模型选择。"""
    target = identifier.strip()
    if not target:
        raise ValueError("请输入要添加的账号、群组或会话标识。")
    if target in settings:
        return f"{target} 已拥有 Plus 权限。"
    settings[target] = "auto"
    return f"已为 {target} 添加 Plus 权限。"


def revoke_paid_access(settings: MutableMapping[str, object], identifier: str) -> str:
    """撤销一个稳定标识的 Plus 使用资格。"""
    target = identifier.strip()
    if not target:
        raise ValueError("请输入要删除的账号、群组或会话标识。")
    if target not in settings or target == "status":
        return f"{target} 不在 Plus 列表中。"
    del settings[target]
    return f"已删除 {target} 的 Plus 权限。"
