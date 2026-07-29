import unittest

from aiohttp import web
from aiohttp.test_utils import TestServer

from ChatGPTWeb.service import ChatRequest

from nonebot_plugin_gpt.remote_service import RemoteChatService


class RemoteChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.personas = {}
        self.requests = []
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

        app.router.add_get("/v1/bot/personas", list_personas)
        app.router.add_put("/v1/bot/personas", upsert_persona)
        app.router.add_delete("/v1/bot/personas", delete_persona)
        app.router.add_post("/v1/bot/persona", get_persona)
        app.router.add_post("/v1/bot/chat", chat)
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
