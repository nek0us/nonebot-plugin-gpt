import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
event_scope = importlib.import_module("nonebot_plugin_gpt.event_scope")


def make_event(module: str, **values):
    event_type = type("FakeEvent", (), {"__module__": module})
    event = event_type()
    event.get_session_id = lambda: values.pop("session_id", "user-1")
    for name, value in values.items():
        setattr(event, name, value)
    return event


class EventScopeTests(unittest.TestCase):
    def test_group_scope_excludes_the_sender_from_onebot_session(self):
        event = make_event(
            "nonebot.adapters.onebot.v11.event",
            group_id=100,
            session_id="group_100_alice",
        )

        scope = event_scope.resolve_event_scope(event)

        self.assertEqual(scope.identifier, "onebot.v11:group:100")
        self.assertTrue(scope.is_shared)

    def test_channel_scope_keeps_guild_and_channel(self):
        event = make_event(
            "nonebot.adapters.qq.event",
            guild_id="guild-1",
            channel_id="channel-2",
        )

        scope = event_scope.resolve_event_scope(event)

        self.assertEqual(scope.identifier, "qq:channel:guild-1:channel-2")
        self.assertTrue(scope.is_shared)

    def test_private_scope_is_namespaced(self):
        event = make_event("nonebot.adapters.telegram.event", session_id="alice")

        scope = event_scope.resolve_event_scope(event)

        self.assertEqual(scope.identifier, "telegram:private:alice")
        self.assertTrue(scope.is_private)

    def test_channel_object_uses_its_own_type(self):
        event = make_event(
            "nonebot.adapters.satori.event",
            channel=types.SimpleNamespace(id="dm-1", type="DIRECT"),
        )

        scope = event_scope.resolve_event_scope(event)

        self.assertEqual(scope.identifier, "satori:private:dm-1")
        self.assertTrue(scope.is_private)

    def test_group_speaker_prompt_keeps_name_and_identity_as_metadata(self):
        event = make_event(
            "nonebot.adapters.onebot.v11.event",
            group_id=100,
            session_id="group_100_alice",
            sender=types.SimpleNamespace(card="小明", nickname="明明"),
        )
        event.get_user_id = lambda: "42"

        prompt = event_scope.format_group_speaker_prompt(event, "你好")

        self.assertIn('"speaker_id": "onebot.v11:user:42"', prompt)
        self.assertIn('"speaker_name": "小明"', prompt)
        self.assertTrue(prompt.endswith("用户消息：你好"))
