"""智能体运行期的无敏感审计记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class AgentAuditEvent:
    """只包含固定事件标签的审计条目，不记录任务、理由或用户输入。"""

    at: str
    action: str
    subject: str
    permission: str = ""


class AgentAuditLog:
    """有界的进程内审计日志；重启后自然清空。"""

    def __init__(self, limit: int = 200):
        self._limit = limit
        self._events: list[AgentAuditEvent] = []

    def record(self, action: str, subject: str, permission: str = "") -> None:
        self._events.append(AgentAuditEvent(
            at=datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
            action=action,
            subject=subject,
            permission=permission,
        ))
        if len(self._events) > self._limit:
            del self._events[:-self._limit]

    def format(self, limit: int = 20) -> str:
        events = self._events[-max(1, min(limit, 50)):]
        if not events:
            return "当前运行尚无智能体审计记录。"
        lines = ["智能体审计（仅当前运行）"]
        for event in reversed(events):
            detail = f"{event.action}：{event.subject}"
            if event.permission:
                detail += f"（{event.permission}）"
            lines.append(f"{event.at} {detail}")
        return "\n".join(lines)
