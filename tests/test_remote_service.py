import unittest

from aiohttp import web
from aiohttp.test_utils import TestServer

from ChatGPTWeb import AgentState, AgentTool, AgentToolResult
from ChatGPTWeb.service import ChatRequest

from nonebot_plugin_gpt.remote_service import RemoteChatService


class RemoteChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.personas = {}
        self.requests = []
        self.response_requests = []
        app = web.Application()

        async def list_personas(_request):
            return web.json_response({"personas": list(self.personas.values())})

        async def upsert_persona(request):
            value = await request.json()
            self.personas[value["name"]] = value
            return web.json_response({"ok": True})

        async def delete_persona(request):
            value = await request.json()
            self.personas.pop(value["name"], None)
            return web.json_response({"ok": True})

        async def get_persona(request):
            value = await request.json()
            persona = self.personas.get(value["name"], {})
            return web.json_response({"prompt": persona.get("value", "")})

        async def chat(request):
            self.requests.append(await request.json())
            return web.json_response({
                "ok": True,
                "text": "remote response",
                "conversation_id": "conversation-1",
                "message_id": "message-1",
                "used_model": "auto",
                "account": "shared@example.com",
                "image_urls": [],
                "usage": {},
                "metadata": {},
                "errors": [],
            })

        async def capabilities(_request):
            return web.json_response({
                "runtime": {
                    "readiness": "ready",
                    "accounts": {"configured": 3, "available": 2},
                },
            })

        async def responses(request):
            payload = await request.json()
            self.response_requests.append(payload)
            if payload.get("previous_response_id"):
                return web.json_response({
                    "id": "resp-final",
                    "status": "completed",
                    "model": "gpt-agent",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                    "output_text": "tool result reviewed",
                    "output": [{
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "tool result reviewed"}],
                    }],
                })
            return web.json_response({
                "id": "resp-tool",
                "status": "completed",
                "model": "gpt-agent",
                "usage": {"input_tokens": 2, "output_tokens": 1},
                "output": [{
                    "type": "function_call",
                    "call_id": "call-read",
                    "name": "workspace.read_text",
                    "arguments": '{"path":"README.md"}',
                }],
            })

        app.router.add_get("/v1/bot/personas", list_personas)
        app.router.add_put("/v1/bot/personas", upsert_persona)
        app.router.add_delete("/v1/bot/personas", delete_persona)
        app.router.add_post("/v1/bot/persona", get_persona)
        app.router.add_post("/v1/bot/chat", chat)
        app.router.add_post("/v1/bot/responses", responses)
        app.router.add_get("/v1/bot/capabilities", capabilities)
        self.server = TestServer(app)
        await self.server.start_server()
        # Operators may enter either the server root or an explicit /v1 URL.
        base_url = str(self.server.make_url("/")).rstrip("/")
        self.service = RemoteChatService(
            base_url,
            "bot-secret",
            personas=[{"name": "local", "value": "local prompt"}],
        )

    async def asyncTearDown(self):
        await self.service.close()
        await self.server.close()

    async def test_syncs_personas_and_adapts_chat_results(self):
        await self.service.start()
        self.assertEqual(self.personas["local"]["value"], "local prompt")
        self.assertEqual(await self.service.get_persona_prompt("local"), "local prompt")

        await self.service.add_personality({"name": "new", "value": "new prompt"})
        result = await self.service.send(ChatRequest(prompt="hello", model="auto"))
        self.assertEqual(self.personas["new"]["value"], "new prompt")
        await self.service.del_personality("new")

        self.assertEqual(result.text, "remote response")
        self.assertEqual(result.account, "shared@example.com")
        self.assertEqual(self.requests[-1]["prompt"], "hello")
        self.assertNotIn("new", self.personas)

    async def test_status_uses_coarse_remote_pool_totals(self):
        status = await self.service.get_account_status()

        self.assertEqual(status["account_summary"], {
            "configured": 3,
            "available": 2,
            "attention": 1,
        })
        self.assertTrue(status["accounts"][0]["shared_core"])

    async def test_agent_turn_uses_bot_responses_cursor(self):
        tool = AgentTool(
            "workspace.read_text",
            "Read a text file in the workspace.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )

        first = await self.service.agent_turn(
            "read the README",
            [tool],
            state=AgentState(model="auto"),
        )
        second = await self.service.agent_turn(
            "",
            [tool],
            state=first.state,
            tool_result=AgentToolResult("workspace.read_text", "README content"),
        )

        self.assertTrue(first.ok)
        self.assertEqual(first.decision.kind, "tool_call")
        self.assertEqual(first.decision.arguments, {"path": "README.md"})
        self.assertEqual(first.state.conversation_id, "responses:resp-tool")
        self.assertEqual(first.state.parent_message_id, "call-read")
        self.assertTrue(second.ok)
        self.assertEqual(second.decision.answer, "tool result reviewed")
        self.assertIn("tools", self.response_requests[0])
        self.assertEqual(self.response_requests[1]["previous_response_id"], "resp-tool")
        self.assertEqual(self.response_requests[1]["input"][0]["call_id"], "call-read")
