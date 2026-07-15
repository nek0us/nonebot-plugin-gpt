"""供 ChatService 调用方使用的适配器无关会话状态。"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nonebot.adapters import Event

from .event_scope import resolve_event_scope, resolve_participant_identity


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ConversationKey:
    """逻辑会话的稳定标识；群聊共享，私聊按用户隔离。"""

    session_id: str
    user_id: str

    @classmethod
    def from_event(cls, event: Event) -> "ConversationKey":
        scope = resolve_event_scope(event)
        # 群、频道等共享范围必须只保留范围本身；若把发送者拼进键中，
        # 每位成员都会被错误分配到独立的 ChatGPT 会话。
        user_id = "" if scope.is_shared else resolve_participant_identity(event)
        return cls(session_id=scope.identifier, user_id=user_id)

    @property
    def value(self) -> str:
        return f"{self.session_id}:{self.user_id}" if self.user_id else self.session_id


@dataclass
class ConversationCheckpoint:
    """一个逻辑会话内由自动压缩产生的物理会话检查点。"""

    conversation_id: str
    parent_message_id: str = ""
    model: str = "auto"
    reason: str = "compaction"
    created_at: str = field(default_factory=_now)
    summary: str = ""


@dataclass
class ConversationState:
    """用户可切换的逻辑会话及其当前物理会话位置。"""

    conversation_id: str = ""
    parent_message_id: str = ""
    model: str = "auto"
    metadata: dict[str, Any] = field(default_factory=dict)
    logical_id: str = ""
    owner_key: str = ""
    label: str = ""
    persona_name: str = ""
    persona_prompt: str = ""
    checkpoints: list[ConversationCheckpoint] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass
class _ConversationArchive:
    bindings: dict[str, str] = field(default_factory=dict)
    sessions: dict[str, ConversationState] = field(default_factory=dict)


class ConversationStore:
    """使用原子写入的轻量 JSON 跨适配器逻辑会话仓库。"""

    def __init__(self, path: Path):
        self._path = path
        self._lock = asyncio.Lock()

    @staticmethod
    def _state_from_dict(value: dict[str, Any], owner_key: str = "") -> ConversationState:
        checkpoints = []
        for checkpoint in value.get("checkpoints", []):
            if isinstance(checkpoint, dict) and checkpoint.get("conversation_id"):
                checkpoints.append(ConversationCheckpoint(
                    conversation_id=str(checkpoint["conversation_id"]),
                    parent_message_id=str(checkpoint.get("parent_message_id", "")),
                    model=str(checkpoint.get("model", "auto")),
                    reason=str(checkpoint.get("reason", "compaction")),
                    created_at=str(checkpoint.get("created_at", _now())),
                    summary=str(checkpoint.get("summary", "")),
                ))
        return ConversationState(
            logical_id=str(value.get("logical_id", "")),
            owner_key=str(value.get("owner_key", owner_key)),
            label=str(value.get("label", "")),
            conversation_id=str(value.get("conversation_id", "")),
            parent_message_id=str(value.get("parent_message_id", "")),
            model=str(value.get("model", "auto")),
            persona_name=str(value.get("persona_name", "")),
            persona_prompt=str(value.get("persona_prompt", "")),
            metadata=value.get("metadata", {}) if isinstance(value.get("metadata"), dict) else {},
            checkpoints=checkpoints,
            created_at=str(value.get("created_at", _now())),
            updated_at=str(value.get("updated_at", _now())),
        )

    def _read_unlocked(self) -> _ConversationArchive:
        if not self._path.exists() or not self._path.stat().st_size:
            return _ConversationArchive()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _ConversationArchive()
        if not isinstance(raw, dict):
            return _ConversationArchive()

        if isinstance(raw.get("bindings"), dict) and isinstance(raw.get("sessions"), dict):
            sessions = {
                logical_id: self._state_from_dict(value)
                for logical_id, value in raw["sessions"].items()
                if isinstance(logical_id, str) and isinstance(value, dict)
            }
            bindings = {
                key: logical_id
                for key, logical_id in raw["bindings"].items()
                if isinstance(key, str) and isinstance(logical_id, str) and logical_id in sessions
            }
            return _ConversationArchive(bindings=bindings, sessions=sessions)

        # 兼容第一版仓库：每个键只有一个活动物理会话。
        archive = _ConversationArchive()
        for owner_key, value in raw.items():
            if not isinstance(owner_key, str) or not isinstance(value, dict):
                continue
            state = self._state_from_dict(value, owner_key)
            state.logical_id = state.logical_id or uuid.uuid4().hex
            archive.bindings[owner_key] = state.logical_id
            archive.sessions[state.logical_id] = state
        return archive

    def _write_unlocked(self, archive: _ConversationArchive) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        payload = {
            "version": 2,
            "bindings": archive.bindings,
            "sessions": {logical_id: asdict(state) for logical_id, state in archive.sessions.items()},
        }
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary_path, self._path)

    async def get(self, key: ConversationKey) -> ConversationState:
        async with self._lock:
            archive = self._read_unlocked()
            logical_id = archive.bindings.get(key.value, "")
            return archive.sessions.get(logical_id, ConversationState(owner_key=key.value))

    async def save(self, key: ConversationKey, state: ConversationState) -> ConversationState:
        async with self._lock:
            archive = self._read_unlocked()
            state.logical_id = state.logical_id or archive.bindings.get(key.value, "") or uuid.uuid4().hex
            state.owner_key = key.value
            state.updated_at = _now()
            archive.sessions[state.logical_id] = state
            archive.bindings[key.value] = state.logical_id
            self._write_unlocked(archive)
            return state

    async def create(self, key: ConversationKey, label: str = "") -> ConversationState:
        return await self.save(
            key,
            ConversationState(logical_id=uuid.uuid4().hex, owner_key=key.value, label=label),
        )

    async def list(self, key: ConversationKey) -> list[ConversationState]:
        async with self._lock:
            archive = self._read_unlocked()
            return sorted(
                (state for state in archive.sessions.values() if state.owner_key == key.value),
                key=lambda state: state.updated_at,
                reverse=True,
            )

    async def switch(self, key: ConversationKey, logical_id: str) -> ConversationState:
        async with self._lock:
            archive = self._read_unlocked()
            state = archive.sessions.get(logical_id)
            if not state or state.owner_key != key.value:
                raise KeyError("逻辑会话不存在或不属于当前会话")
            archive.bindings[key.value] = logical_id
            self._write_unlocked(archive)
            return state

    async def add_checkpoint(
        self,
        key: ConversationKey,
        state: ConversationState,
        *,
        conversation_id: str,
        parent_message_id: str,
        model: str,
        summary: str,
    ) -> ConversationState:
        state.conversation_id = conversation_id
        state.parent_message_id = parent_message_id
        state.model = model or state.model
        state.checkpoints.append(ConversationCheckpoint(
            conversation_id=conversation_id,
            parent_message_id=parent_message_id,
            model=state.model,
            summary=summary,
        ))
        return await self.save(key, state)

    async def clear(self, key: ConversationKey) -> None:
        async with self._lock:
            archive = self._read_unlocked()
            logical_id = archive.bindings.pop(key.value, "")
            if logical_id:
                archive.sessions.pop(logical_id, None)
            self._write_unlocked(archive)
