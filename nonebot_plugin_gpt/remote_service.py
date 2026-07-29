"""HTTP-backed ChatService adapter for a separately managed ChatGPTWeb core."""

from __future__ import annotations

import base64
import asyncio
import inspect
import json
from typing import Any, AsyncIterator

from aiohttp import ClientSession, ClientTimeout

from ChatGPTWeb.api import ChatStreamEvent
from ChatGPTWeb.content import build_chat_content
from ChatGPTWeb.config import Personality
from ChatGPTWeb.service import ChatRequest, ChatResult, ConversationContextEstimate


class RemoteCoreError(RuntimeError):
    """A safe transport error from the configured shared core service."""


class RemoteChatService:
    """Expose the local ``ChatService`` surface through the scoped Bot API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: int = 90,
        personas: list[dict[str, str]] | None = None,
    ):
        base = base_url.strip().rstrip("/")
        if not base:
            raise ValueError("remote core base URL must not be empty")
        if not api_key.strip():
            raise ValueError("remote core API key must not be empty")
        self._base_url = base if base.endswith("/v1") else f"{base}/v1"
        self._api_key = api_key.strip()
        self._timeout = ClientTimeout(total=max(5, timeout_seconds))
        self._session: ClientSession | None = None
        self.personality = Personality(personas or [])
        self._initialized = False
        self._sync_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _client(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(timeout=self._timeout)
        return self._session

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _json(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        method: str | None = None,
    ) -> dict[str, Any]:
        client = await self._client()
        async with client.request(
            method or ("POST" if payload is not None else "GET"),
            self._url(path),
            headers=self._headers(),
            json=payload,
        ) as response:
            body = await response.text()
            if response.status >= 400:
                raise RemoteCoreError(f"shared core returned HTTP {response.status}: {body[:400]}")
            try:
                value = json.loads(body)
            except json.JSONDecodeError as error:
                raise RemoteCoreError("shared core returned invalid JSON") from error
            if not isinstance(value, dict):
                raise RemoteCoreError("shared core returned an invalid response object")
            return value

    async def start(self) -> None:
        """Merge persisted plugin personas into this Bot key's core namespace."""
        async with self._sync_lock:
            if self._initialized:
                return
            value = await self._json("/bot/personas")
            remote = value.get("personas")
            remote_items = remote if isinstance(remote, list) else []
            merged = {
                item["name"]: {"name": item["name"], "value": item["value"]}
                for item in remote_items
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("value"), str)
            }
            # The plugin's data directory is the source of truth for its local
            # visibility metadata, so its prompt text wins on first connection.
            for item in self.personality.init_list:
                merged[item["name"]] = item
            self.personality.replace_data(list(merged.values()))
            for item in self.personality.init_list:
                await self._json("/bot/personas", item, method="PUT")
            self._initialized = True

    async def _ensure_started(self) -> None:
        if not self._initialized:
            await self.start()

    @staticmethod
    def _request_payload(request: ChatRequest) -> dict[str, Any]:
        return {
            "prompt": request.prompt,
            "conversation_id": request.conversation_id,
            "parent_message_id": request.parent_message_id,
            "model": request.model,
            "attachments": [
                {
                    "name": item.name,
                    "content_base64": base64.b64encode(item.content).decode("ascii"),
                }
                for item in request.files
            ],
            "web_search": request.web_search,
            "deep_research": request.deep_research,
            "prefer_paid_account": request.prefer_paid_account,
            "stream_idle_timeout_seconds": request.stream_idle_timeout_seconds,
            "stream_status_interval_seconds": request.stream_status_interval_seconds,
            "operation": request.operation.value,
            "reference": request.reference,
        }

    @staticmethod
    def _result(value: dict[str, Any], request: ChatRequest) -> ChatResult:
        raw_text = value.get("text") if isinstance(value.get("text"), str) else ""
        images = value.get("image_urls") if isinstance(value.get("image_urls"), list) else []
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        errors = value.get("errors") if isinstance(value.get("errors"), list) else []
        return ChatResult(
            ok=bool(value.get("ok")),
            text=raw_text,
            conversation_id=str(value.get("conversation_id") or request.conversation_id),
            message_id=str(value.get("message_id") or ""),
            requested_model=str(value.get("requested_model") or request.model),
            used_model=str(value.get("used_model") or ""),
            image_urls=[item for item in images if isinstance(item, str)],
            usage=dict(value.get("usage") or {}),
            metadata=metadata,
            errors=[item for item in errors if isinstance(item, dict)],
            account=str(value.get("account") or ""),
            content=build_chat_content(raw_text, images, metadata),
        )

    async def send(self, request: ChatRequest) -> ChatResult:
        await self._ensure_started()
        value = await self._json("/bot/chat", self._request_payload(request))
        return self._result(value, request)

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatStreamEvent]:
        await self._ensure_started()
        client = await self._client()
        async with client.post(
            self._url("/bot/chat/stream"),
            headers=self._headers(),
            json=self._request_payload(request),
        ) as response:
            if response.status >= 400:
                raise RemoteCoreError(f"shared core returned HTTP {response.status}: {(await response.text())[:400]}")
            event_name = ""
            data_lines: list[str] = []
            async for raw_line in response.content:
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line:
                    if event_name == "chatgptweb.event" and data_lines:
                        try:
                            value = json.loads("\n".join(data_lines))
                        except json.JSONDecodeError as error:
                            raise RemoteCoreError("shared core emitted invalid stream JSON") from error
                        if not isinstance(value, dict):
                            raise RemoteCoreError("shared core emitted an invalid stream event")
                        yield ChatStreamEvent(
                            type=str(value.get("type") or "error"),
                            text=str(value.get("text") or ""),
                            raw_text=str(value.get("raw_text") or ""),
                            message_id=str(value.get("message_id") or ""),
                            conversation_id=str(value.get("conversation_id") or ""),
                            image_urls=[item for item in value.get("image_urls", []) if isinstance(item, str)],
                            model=str(value.get("model") or ""),
                            usage=dict(value.get("usage") or {}),
                            metadata=dict(value.get("metadata") or {}),
                        )
                    event_name = ""
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())

    async def stream_to_callback(self, request: ChatRequest, callback) -> ChatResult:
        chunks: list[str] = []
        image_urls: list[str] = []
        final_event: ChatStreamEvent | None = None
        errors: list[dict[str, Any]] = []
        last_event: ChatStreamEvent | None = None
        async for event in self.stream(request):
            last_event = event
            if event.type == "delta":
                chunks.append(event.text)
            elif event.type in {"image", "image_pending"}:
                image_urls = event.image_urls.copy()
            elif event.type == "final":
                final_event = event
                if event.image_urls:
                    image_urls = event.image_urls.copy()
            elif event.type == "error":
                errors.append({
                    "kind": str(event.metadata.get("error_kind") or "stream_error"),
                    "message": event.text,
                    "retryable": bool(event.metadata.get("retryable", False)),
                })
            outcome = callback(event)
            if inspect.isawaitable(outcome):
                await outcome
        terminal = final_event or last_event
        text = final_event.text if final_event and final_event.text else "".join(chunks)
        metadata = dict(terminal.metadata) if terminal else {}
        raw_text = final_event.raw_text if final_event and final_event.raw_text else text
        return ChatResult(
            ok=bool(final_event and not errors),
            text=text,
            conversation_id=terminal.conversation_id if terminal else request.conversation_id,
            message_id=terminal.message_id if terminal else "",
            requested_model=request.model,
            used_model=terminal.model if terminal else "",
            image_urls=image_urls,
            usage=dict(terminal.usage) if terminal else {},
            metadata=metadata,
            errors=errors,
            content=build_chat_content(raw_text, image_urls, metadata),
        )

    async def get_history(self, conversation_id: str) -> list[dict[str, Any]]:
        await self._ensure_started()
        value = await self._json("/bot/history", {"conversation_id": conversation_id})
        history = value.get("history")
        return [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []

    async def get_persona_prompt(self, name: str) -> str:
        await self._ensure_started()
        value = await self._json("/bot/persona", {"name": name})
        return str(value.get("prompt") or "")

    async def add_personality(self, personality: dict[str, Any]) -> None:
        await self._ensure_started()
        name = personality.get("name")
        value = personality.get("value")
        if not isinstance(name, str) or not name.strip() or not isinstance(value, str):
            raise ValueError("personality requires a non-empty name and string value")
        normalized = {"name": name.strip(), "value": value}
        await self._json("/bot/personas", normalized, method="PUT")
        self.personality.add_dict_to_list(normalized)

    async def del_personality(self, name: str) -> str:
        await self._ensure_started()
        await self._json("/bot/personas", {"name": name}, method="DELETE")
        self.personality.del_data_by_name(name)
        return self.personality.show_name()

    async def estimate_context(
        self,
        conversation_id: str,
        *,
        model: str = "",
        account: str = "",
    ) -> ConversationContextEstimate:
        await self._ensure_started()
        value = await self._json("/bot/context-estimate", {
            "conversation_id": conversation_id,
            "model": model,
            "account": account,
        })
        estimate = value.get("estimate")
        if not isinstance(estimate, dict):
            raise RemoteCoreError("shared core returned no context estimate")
        return ConversationContextEstimate(**estimate)

    async def get_model_catalog(self, fetch_remote: bool = False) -> dict[str, Any]:
        # The standard endpoint is intentionally unavailable to a Bot key.
        # Context estimation only needs a coarse fallback in remote mode.
        return {"accounts": [], "fetch_remote": fetch_remote}

    async def get_runtime_health(self) -> dict[str, Any]:
        return await self._json("/bot/capabilities")

    async def get_account_status(self) -> dict[str, Any]:
        # Bot keys intentionally receive only coarse availability data. Keep
        # the real pool totals, but never disclose individual account details
        # through a bot-scoped key.
        capability = await self.get_runtime_health()
        runtime = capability.get("runtime") if isinstance(capability, dict) else {}
        accounts = runtime.get("accounts") if isinstance(runtime, dict) else {}
        configured = accounts.get("configured") if isinstance(accounts, dict) else 0
        available_count = accounts.get("available") if isinstance(accounts, dict) else 0
        configured = configured if isinstance(configured, int) and not isinstance(configured, bool) else 0
        available_count = available_count if isinstance(available_count, int) and not isinstance(available_count, bool) else 0
        available_count = max(0, min(configured, available_count))
        summary = {
            "configured": configured,
            "available": available_count,
            "attention": max(0, configured - available_count),
        }
        available = bool(isinstance(runtime, dict) and runtime.get("readiness") == "ready")
        return {"accounts": [{
            "email": "shared-core",
            "available": available,
            "status": "Ready" if available else "Update",
            "conversation_count": 0,
            "observed_model_count": 0,
            "usage": {},
            "runtime": {"context_ready": available, "page_ready": available},
            "shared_core": True,
        }], "account_summary": summary}
