"""HTTP-backed ChatService adapter for a separately managed ChatGPTWeb core."""

from __future__ import annotations

import base64
import asyncio
import binascii
import inspect
import json
from typing import Any, AsyncIterator

from aiohttp import ClientSession, ClientTimeout

from ChatGPTWeb import AgentDecision, AgentService, AgentState, AgentTool, AgentToolResult, AgentTurn
from ChatGPTWeb.api import ChatStreamEvent
from ChatGPTWeb.content import build_chat_content
from ChatGPTWeb.config import IOFile, Personality
from ChatGPTWeb.service import ChatRequest, ChatResult, ConversationContextEstimate


class RemoteCoreError(RuntimeError):
    """A safe transport error from the configured shared core service."""


_RESPONSES_CURSOR_PREFIX = "responses:"


class RemoteChatService:
    """Expose the local ``ChatService`` surface through the scoped Bot API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: int = 90,
        personas: list[dict[str, str]] | None = None,
        max_output_file_size: int = 20 * 1024 * 1024,
        max_output_total_size: int = 40 * 1024 * 1024,
        max_output_file_count: int = 8,
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
        self._max_output_file_size = max_output_file_size
        self._max_output_total_size = max_output_total_size
        self._max_output_file_count = max_output_file_count

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
            "required_capabilities": list(
                getattr(request, "required_capabilities", [])
            ),
            "web_search": request.web_search,
            "deep_research": request.deep_research,
            "prefer_paid_account": request.prefer_paid_account,
            "stream_idle_timeout_seconds": request.stream_idle_timeout_seconds,
            "stream_status_interval_seconds": request.stream_status_interval_seconds,
            "operation": request.operation.value,
            "reference": request.reference,
        }

    @staticmethod
    def _safe_file_name(value: Any) -> str:
        name = str(value or "attachment").replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        return name.strip(" .")[:255] or "attachment"

    def _output_files(self, value: Any) -> list[IOFile]:
        files: list[IOFile] = []
        total_size = 0
        if not isinstance(value, list):
            return files
        for item in value[: self._max_output_file_count]:
            if not isinstance(item, dict):
                continue
            encoded = item.get("content_base64")
            if not isinstance(encoded, str):
                continue
            try:
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                continue
            if not content or len(content) > self._max_output_file_size:
                continue
            if total_size + len(content) > self._max_output_total_size:
                break
            declared_mime = (
                item.get("mime_type")
                if isinstance(item.get("mime_type"), str)
                else None
            )
            output_file = IOFile(
                content=content,
                name=self._safe_file_name(item.get("name")),
                mime_type=declared_mime,
            )
            # Older ChatGPTWeb releases overwrite an explicitly supplied MIME
            # type with application/octet-stream when bytes are not sniffable.
            if declared_mime and output_file.mime_type == "application/octet-stream":
                output_file.mime_type = declared_mime
            files.append(output_file)
            total_size += len(content)
        return files

    def _result(self, value: dict[str, Any], request: ChatRequest) -> ChatResult:
        raw_text = value.get("text") if isinstance(value.get("text"), str) else ""
        images = value.get("image_urls") if isinstance(value.get("image_urls"), list) else []
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        errors = value.get("errors") if isinstance(value.get("errors"), list) else []
        result = ChatResult(
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
        result.files = self._output_files(value.get("files"))
        return result

    async def send(self, request: ChatRequest) -> ChatResult:
        await self._ensure_started()
        value = await self._json("/bot/chat", self._request_payload(request))
        return self._result(value, request)

    @staticmethod
    def _responses_tools(tools: list[AgentTool]) -> list[dict[str, Any]]:
        return [{
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        } for tool in tools]

    @staticmethod
    def _response_text(value: dict[str, Any]) -> str:
        text = value.get("output_text")
        if isinstance(text, str):
            return text
        output = value.get("output")
        if not isinstance(output, list):
            return ""
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "\n".join(chunks)

    @staticmethod
    def _response_function_call(value: dict[str, Any]) -> dict[str, Any] | None:
        output = value.get("output")
        if not isinstance(output, list):
            return None
        for item in output:
            if isinstance(item, dict) and item.get("type") == "function_call":
                return item
        return None

    async def agent_turn(
        self,
        task: str,
        tools: list[AgentTool],
        *,
        state: AgentState | None = None,
        tool_result: AgentToolResult | None = None,
        model: str = "auto",
    ) -> AgentTurn:
        """Use the Bot-scoped Responses bridge for one host-executed turn.

        The core owns the opaque Responses cursor.  Its response and function
        call IDs are encoded in the existing plugin-only ``AgentState`` cursor,
        so the local approval and scheduler flow can continue unchanged.
        """
        await self._ensure_started()
        state = state or AgentState(model=model)
        selected_model = model if model and model != "auto" else state.model or "auto"
        active_task = task.strip() or state.task
        previous_response_id = ""
        if state.conversation_id.startswith(_RESPONSES_CURSOR_PREFIX):
            previous_response_id = state.conversation_id[len(_RESPONSES_CURSOR_PREFIX):]

        try:
            if previous_response_id:
                if tool_result is None or not state.parent_message_id:
                    return AgentTurn(
                        False,
                        state,
                        AgentDecision("error", error="remote_agent_cursor_requires_tool_result"),
                        requested_model=selected_model,
                    )
                payload: dict[str, Any] = {
                    "model": selected_model,
                    "previous_response_id": previous_response_id,
                    "input": [{
                        "type": "function_call_output",
                        "call_id": state.parent_message_id,
                        "output": tool_result.output[:12000],
                    }],
                }
            else:
                if not active_task:
                    return AgentTurn(
                        False,
                        state,
                        AgentDecision("error", error="remote_agent_task_missing"),
                        requested_model=selected_model,
                    )
                payload = {
                    "model": selected_model,
                    "input": active_task,
                    "tools": self._responses_tools(tools),
                }
            value = await self._json("/bot/responses", payload)
        except RemoteCoreError as error:
            # Permit a rolling upgrade: an older shared core does not expose
            # the Bot-scoped Responses route yet, but can still serve the
            # original Bot chat bridge until the core is updated.
            if "HTTP 404" in str(error):
                return await AgentService(self).turn(
                    task,
                    tools,
                    state=state,
                    tool_result=tool_result,
                    model=selected_model,
                )
            return AgentTurn(
                False,
                state,
                AgentDecision("error", error="remote_agent_request_failed"),
                requested_model=selected_model,
                errors=[{"kind": "remote_agent_request_failed", "message": "shared core Responses request failed"}],
            )

        response_id = value.get("id")
        used_model = value.get("model")
        response_id = response_id if isinstance(response_id, str) else ""
        used_model = used_model if isinstance(used_model, str) and used_model else selected_model
        usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
        if value.get("status") != "completed" or not response_id:
            return AgentTurn(
                False,
                state,
                AgentDecision("error", error="remote_agent_response_failed"),
                requested_model=selected_model,
                used_model=used_model,
                usage=dict(usage),
                errors=[{"kind": "remote_agent_response_failed", "message": "shared core Responses turn failed"}],
            )

        function_call = self._response_function_call(value)
        next_state = AgentState(
            conversation_id=f"{_RESPONSES_CURSOR_PREFIX}{response_id}",
            parent_message_id="",
            model=used_model,
            task=active_task,
        )
        if function_call is not None:
            name = function_call.get("name")
            call_id = function_call.get("call_id")
            arguments = function_call.get("arguments")
            try:
                parsed_arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                parsed_arguments = None
            if (
                not isinstance(name, str)
                or not isinstance(call_id, str)
                or not isinstance(parsed_arguments, dict)
            ):
                return AgentTurn(
                    False,
                    next_state,
                    AgentDecision("error", error="remote_agent_response_invalid"),
                    requested_model=selected_model,
                    used_model=used_model,
                    usage=dict(usage),
                    errors=[{"kind": "remote_agent_response_invalid", "message": "shared core returned an invalid function call"}],
                )
            next_state = AgentState(
                conversation_id=next_state.conversation_id,
                parent_message_id=call_id,
                model=used_model,
                task=active_task,
            )
            return AgentTurn(
                True,
                next_state,
                AgentDecision("tool_call", tool=name, arguments=parsed_arguments, summary=f"请求执行 {name}"),
                requested_model=selected_model,
                used_model=used_model,
                usage=dict(usage),
            )
        return AgentTurn(
            True,
            next_state,
            AgentDecision("final", answer=self._response_text(value)),
            requested_model=selected_model,
            used_model=used_model,
            usage=dict(usage),
        )

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
                        event = ChatStreamEvent(
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
                        event.files = self._output_files(value.get("files"))
                        yield event
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
        files: list[IOFile] = []
        last_event: ChatStreamEvent | None = None
        async for event in self.stream(request):
            last_event = event
            if event.type == "delta":
                chunks.append(event.text)
            elif event.type in {"image", "image_pending"}:
                image_urls = event.image_urls.copy()
            elif event.type == "final":
                final_event = event
                # A reconciled final event is authoritative. It may intentionally
                # replace an earlier private URL with an in-band image file.
                image_urls = event.image_urls.copy()
                if event.files:
                    files = event.files.copy()
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
        result = ChatResult(
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
        result.files = files
        return result

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
        capability_quota = (
            runtime.get("capability_quota")
            if isinstance(runtime, dict)
            and isinstance(runtime.get("capability_quota"), dict)
            else {}
        )
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
            "capability_quota": {
                "shared_core": True,
                **capability_quota,
            },
            "runtime": {"context_ready": available, "page_ready": available},
            "shared_core": True,
        }], "account_summary": summary}
