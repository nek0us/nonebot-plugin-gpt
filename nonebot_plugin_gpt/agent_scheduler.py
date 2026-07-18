"""持久化的受控智能体定时事件调度器。"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time
from typing import Any, Awaitable, Callable
from uuid import uuid4


@dataclass(frozen=True)
class ScheduledReminder:
    """一次等待投递的提醒，不保存模型上下文、凭据或工具结果。"""

    id: str
    due_at: float
    target: dict[str, Any]
    conversation_session_id: str
    conversation_user_id: str
    user_id: str
    content: str
    attempts: int = 0
    created_at: float = field(default_factory=time)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScheduledReminder | None":
        try:
            identifier = str(value["id"])
            due_at = float(value["due_at"])
            target = value["target"]
            if not identifier or not isinstance(target, dict):
                return None
            return cls(
                id=identifier,
                due_at=due_at,
                target=dict(target),
                conversation_session_id=str(value.get("conversation_session_id") or ""),
                conversation_user_id=str(value.get("conversation_user_id") or ""),
                user_id=str(value.get("user_id") or ""),
                content=str(value.get("content") or "")[:2000],
                attempts=max(0, int(value.get("attempts", 0))),
                created_at=float(value.get("created_at", due_at)),
            )
        except (KeyError, TypeError, ValueError):
            return None


ReminderHandler = Callable[[ScheduledReminder], Awaitable[None]]


class AgentScheduler:
    """以 JSON 原子落盘的轻量提醒队列。"""

    def __init__(
        self,
        path: Path,
        handler: ReminderHandler,
        *,
        clock: Callable[[], float] = time,
    ) -> None:
        self._path = path
        self._handler = handler
        self._clock = clock
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._items: dict[str, ScheduledReminder] = {}
        self._worker: asyncio.Task[None] | None = None

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = []
        if not isinstance(raw, list):
            raw = []
        self._items = {
            item.id: item
            for value in raw
            if isinstance(value, dict)
            for item in [ScheduledReminder.from_dict(value)]
            if item is not None
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps([asdict(item) for item in self._items.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self._path)

    async def start(self) -> None:
        async with self._lock:
            if self._worker is not None:
                return
            self._load()
            self._worker = asyncio.create_task(self._run(), name="nonebot-plugin-gpt-agent-scheduler")

    async def close(self) -> None:
        async with self._lock:
            worker, self._worker = self._worker, None
            self._wake.set()
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

    async def schedule(
        self,
        *,
        delay_seconds: int,
        target: dict[str, Any],
        conversation_session_id: str,
        conversation_user_id: str,
        user_id: str,
        content: str,
    ) -> ScheduledReminder:
        if delay_seconds < 1:
            raise ValueError("提醒时间至少为 1 秒。")
        if not isinstance(target, dict) or not target:
            raise ValueError("当前消息没有可用的跨平台投递目标。")
        item = ScheduledReminder(
            id=f"reminder_{uuid4().hex[:12]}",
            due_at=self._clock() + delay_seconds,
            target=dict(target),
            conversation_session_id=conversation_session_id,
            conversation_user_id=conversation_user_id,
            user_id=user_id,
            content=content.strip()[:2000],
        )
        async with self._lock:
            self._items[item.id] = item
            self._save()
            self._wake.set()
        return item

    async def list(self) -> list[ScheduledReminder]:
        async with self._lock:
            return sorted(self._items.values(), key=lambda item: item.due_at)

    async def list_for_user(self, *, user_id: str, conversation_session_id: str) -> list[ScheduledReminder]:
        """返回当前用户在当前聊天范围创建的提醒。"""
        items = await self.list()
        return [
            item for item in items
            if item.user_id == user_id and item.conversation_session_id == conversation_session_id
        ]

    async def cancel_for_user(
        self,
        identifier: str,
        *,
        user_id: str,
        conversation_session_id: str,
    ) -> bool:
        """只允许创建者在原聊天范围取消自己的提醒。"""
        async with self._lock:
            item = self._items.get(identifier)
            if item is None or item.user_id != user_id or item.conversation_session_id != conversation_session_id:
                return False
            self._items.pop(identifier, None)
            self._save()
            self._wake.set()
            return True

    async def _take_due(self) -> list[ScheduledReminder]:
        async with self._lock:
            now = self._clock()
            due = [item for item in self._items.values() if item.due_at <= now]
            if due:
                for item in due:
                    self._items.pop(item.id, None)
                self._save()
            return due

    async def _next_delay(self) -> float | None:
        async with self._lock:
            if not self._items:
                return None
            return max(0.0, min(item.due_at for item in self._items.values()) - self._clock())

    async def _retry(self, item: ScheduledReminder) -> None:
        if item.attempts >= 2:
            return
        retry = ScheduledReminder(
            **{**asdict(item), "due_at": self._clock() + 60, "attempts": item.attempts + 1},
        )
        async with self._lock:
            self._items[retry.id] = retry
            self._save()
            self._wake.set()

    async def _run(self) -> None:
        while True:
            for item in await self._take_due():
                try:
                    await self._handler(item)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await self._retry(item)
            delay = await self._next_delay()
            self._wake.clear()
            try:
                if delay is None:
                    await self._wake.wait()
                else:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except TimeoutError:
                pass
