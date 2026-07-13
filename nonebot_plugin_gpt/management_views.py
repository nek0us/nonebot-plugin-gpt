"""账户与运行状态的跨平台文本视图。"""

from __future__ import annotations

from typing import Any


_PLAN_NAMES = {
    "free": "免费版",
    "plus": "Plus",
    "pro": "Pro",
    "go": "Go",
    "team": "Team",
    "business": "Business",
    "enterprise": "Enterprise",
    "unknown": "未知",
}

_RUNTIME_NAMES = {
    "Ready": "就绪",
    "Working": "工作中",
    "Login": "登录中",
    "Stop": "已停止",
    "Update": "更新中",
}

_FAILURE_ACTIONS = {
    "account_locked": "账号暂不可用，等待上游恢复后再尝试。",
    "bad_credentials": "登录信息已失效，请更新后再重试。",
    "need_verification": "需要完成验证；提交验证码后可手动重试登录。",
    "risk_blocked": "登录被风控拦截，请等待冷却后重试。",
    "rate_limited": "登录请求受限，请等待冷却后重试。",
    "transient": "浏览器或网络暂时异常，可稍后重试。",
    "unknown": "登录尚未完成，请查看本地控制台后决定是否重试。",
}


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _plan_name(account: dict[str, Any]) -> str:
    plan = str(account.get("account_plan", "unknown")).lower()
    return _PLAN_NAMES.get(plan, plan or "未知")


def _runtime_name(account: dict[str, Any]) -> str:
    state = str(account.get("status", ""))
    return _RUNTIME_NAMES.get(state, state or "未知")


def _usage_requests(account: dict[str, Any]) -> int:
    usage = account.get("usage")
    return _as_int(usage.get("requests")) if isinstance(usage, dict) else 0


def _action_for(account: dict[str, Any]) -> str:
    if account.get("manual_disabled"):
        return "已由管理员停用；需要时可在控制台恢复。"
    if account.get("verification"):
        return "等待人工完成登录验证。"
    if account.get("login_retry_pending"):
        return "正在执行手动登录重试。"

    retry_mode = str(account.get("retry_mode", ""))
    if retry_mode == "cooldown":
        seconds = _as_int(account.get("retry_after_seconds"))
        return f"正在冷却，约 {seconds} 秒后可重试。" if seconds else "正在冷却，稍后可重试。"
    if retry_mode in {"manual", "retry"}:
        failure = str(account.get("login_failure_kind", "unknown"))
        return _FAILURE_ACTIONS.get(failure, _FAILURE_ACTIONS["unknown"])
    return ""


def _runtime_summary(account: dict[str, Any]) -> str:
    runtime = account.get("runtime")
    if not isinstance(runtime, dict):
        return ""
    states = []
    if runtime.get("context_ready"):
        states.append("上下文已就绪")
    if runtime.get("page_ready"):
        states.append("页面已就绪")
    recovered = _as_int(runtime.get("recovery_count"))
    if recovered:
        states.append(f"已自动恢复 {recovered} 次")
    return "，".join(states)


def _account_available(account: dict[str, Any]) -> bool:
    return bool(account.get("available"))


def format_account_status(status: dict[str, Any]) -> str:
    """生成不含凭据、验证码和原始登录错误的账户运行摘要。"""
    accounts = status.get("accounts")
    if not isinstance(accounts, list):
        return "账户状态暂不可用。"
    normalized = [account for account in accounts if isinstance(account, dict)]
    if not normalized:
        return "当前没有已配置账户。"

    available_count = sum(_account_available(account) for account in normalized)
    attention_count = sum(bool(_action_for(account)) for account in normalized)
    lines = [
        "ChatGPT 运行状态",
        f"账户 {len(normalized)} 个｜可用 {available_count} 个｜需处理 {attention_count} 个",
    ]
    for index, account in enumerate(normalized, start=1):
        email = str(account.get("email", "未知账户"))
        availability = "可用" if _account_available(account) else "不可用"
        lines.extend([
            "",
            f"[{index}] {email}",
            f"{availability}｜套餐 {_plan_name(account)}｜运行 {_runtime_name(account)}",
            (
                f"会话 {_as_int(account.get('conversation_count'))} 个｜"
                f"已观测模型 {_as_int(account.get('observed_model_count'))} 个｜"
                f"本进程请求 {_usage_requests(account)} 次"
            ),
        ])
        runtime = _runtime_summary(account)
        if runtime:
            lines.append(f"运行时：{runtime}")
        action = _action_for(account)
        if action:
            lines.append(f"处理：{action}")
    return "\n".join(lines)
