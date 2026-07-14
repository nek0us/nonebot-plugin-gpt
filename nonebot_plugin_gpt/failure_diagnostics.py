"""管理员可见的聊天失败分类汇总，不保存用户消息或底层错误文本。"""

from __future__ import annotations

from collections import Counter

from ChatGPTWeb import ChatResult


_CATEGORY_BY_KIND = {
    "startup_timeout": "启动或请求超时",
    "continue_chat_timeout": "启动或请求超时",
    "send_retry_max": "启动或请求超时",
    "no_available_session": "会话不可用",
    "no_ready_session": "会话不可用",
    "conversation_session_missing": "会话不可用",
    "conversation_session_stopped": "会话不可用",
    "conversation_session_not_ready": "会话不可用",
    "session_not_found": "会话不可用",
    "session_runtime_unavailable": "会话不可用",
    "risk_blocked": "账号登录或风控",
    "token_expired": "账号登录或风控",
    "no_plus_account": "高级模型资源不可用",
    "requirements_token_unavailable": "网页验证失败",
    "proof_token_unavailable": "网页验证失败",
    "turnstile_token_unavailable": "网页验证失败",
    "arkose_token_unavailable": "网页验证失败",
}


class ChatFailureDiagnostics:
    """维护有界的失败类别计数，重启插件后自然清空。"""

    def __init__(self, limit: int = 200):
        self._limit = limit
        self._categories: list[str] = []

    def record_result(self, result: ChatResult) -> None:
        if result.ok:
            return
        kinds = [
            str(error.get("kind", ""))
            for error in result.errors
            if isinstance(error, dict)
        ]
        category = next(
            (_CATEGORY_BY_KIND[kind] for kind in kinds if kind in _CATEGORY_BY_KIND),
            "其他请求失败",
        )
        self._record(category)

    def record_exception(self) -> None:
        self._record("插件运行异常")

    def format(self) -> str:
        if not self._categories:
            return ""
        counts = Counter(self._categories)
        details = "；".join(f"{category} {count}" for category, count in counts.most_common())
        return f"本次运行聊天失败 {len(self._categories)} 次（{details}）"

    def _record(self, category: str) -> None:
        self._categories.append(category)
        if len(self._categories) > self._limit:
            del self._categories[:-self._limit]
