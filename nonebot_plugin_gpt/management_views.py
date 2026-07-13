"""账户与运行状态的跨平台文本投影。"""

from __future__ import annotations

from typing import Any


def format_account_status(status: dict[str, Any]) -> str:
    """生成不含凭据和原始登录错误的账户状态摘要。"""
    accounts = status.get("accounts")
    if not isinstance(accounts, list):
        return "账户状态暂不可用。"
    if not accounts:
        return "当前没有已配置账户。"
    lines = ["ChatGPT 账户状态"]
    for index, account in enumerate(accounts, start=1):
        if not isinstance(account, dict):
            continue
        email = str(account.get("email", "未知账户"))
        state = str(account.get("status", "unknown"))
        available = "可用" if account.get("available") else "不可用"
        plan = str(account.get("account_plan", "unknown"))
        conversation_count = account.get("conversation_count", 0)
        guidance = str(account.get("login_guidance", ""))
        lines.append(
            f"{index}. {email}：{available}，状态 {state}，套餐 {plan}，会话 {conversation_count}"
        )
        if guidance:
            lines.append(f"   登录提示：{guidance}")
    return "\n".join(lines)
