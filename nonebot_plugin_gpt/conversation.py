"""供 ChatService 调用方使用的适配器无关会话状态。"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nonebot.adapters import Event


@dataclass(frozen=True)
class ConversationKey:
    """同一 NoneBot 会话中单个用户的稳定标识。"""

    session_id: str
    user_id: str

    @classmethod
    def from_event(cls, event: Event) -> "ConversationKey":
        return cls(session_id=event.get_session_id(), user_id=event.get_user_id())

    @property
    def value(self) -> str:
        return f"{self.session_id}:{self.user_id}"


@dataclass
class ConversationState:
    """继续一段 ChatGPT 会话所需的最小上游状态。"""

    conversation_id: str = ""
    parent_message_id: str = ""
    model: str = "auto"
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationStore:
    """使用原子写入的轻量 JSON 跨适配器会话仓库。"""

    def __init__(self, path: Path):
        self._path = path
        self._lock = asyncio.Lock()

    def _read_unlocked(self) -> dict[str, ConversationState]:
        if not self._path.exists() or not self._path.stat().st_size:
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        states: dict[str, ConversationState] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, dict):
                states[key] = ConversationState(
                    conversation_id=str(value.get("conversation_id", "")),
                    parent_message_id=str(value.get("parent_message_id", "")),
                    model=str(value.get("model", "auto")),
                    metadata=value.get("metadata", {}) if isinstance(value.get("metadata"), dict) else {},
                )
        return states

    def _write_unlocked(self, states: dict[str, ConversationState]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        payload = {key: asdict(state) for key, state in states.items()}
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary_path, self._path)

    async def get(self, key: ConversationKey) -> ConversationState:
        async with self._lock:
            return self._read_unlocked().get(key.value, ConversationState())

    async def save(self, key: ConversationKey, state: ConversationState) -> None:
        async with self._lock:
            states = self._read_unlocked()
            states[key.value] = state
            self._write_unlocked(states)

    async def clear(self, key: ConversationKey) -> None:
        async with self._lock:
            states = self._read_unlocked()
            if key.value in states:
                del states[key.value]
                self._write_unlocked(states)
