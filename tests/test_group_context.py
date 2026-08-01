import importlib
import sys
import types
import unittest
from pathlib import Path

from nonebot_plugin_alconna.uniseg import At, Image, Text, UniMessage


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
group_context = importlib.import_module("nonebot_plugin_gpt.group_context")


class Clock:
    def __init__(self, value: float = 1000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


def make_event(user_id: str, *, group_id: str = "100", name: str = ""):
    event_type = type(
        "FakeEvent",
        (),
        {"__module__": "nonebot.adapters.onebot.v11.event"},
    )
    event = event_type()
    event.group_id = group_id
    event.self_id = "999"
    event.sender = types.SimpleNamespace(card=name)
    event.get_user_id = lambda: user_id
    event.get_session_id = lambda: f"group_{group_id}_{user_id}"
    return event


class GroupContextTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.buffer = group_context.GroupContextBuffer(
            max_entries_per_scope=20,
            retention_seconds=3600,
            store_images=True,
            clock=self.clock,
        )

    def test_cursor_keeps_only_messages_after_the_previous_chat(self):
        first = make_event("1", name="Alice")
        current = make_event("2", name="Bob")
        self.buffer.capture(first, UniMessage.text("first ambient message"))

        selection = self.buffer.select_before(
            current,
            UniMessage.text("call the bot"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )

        self.assertEqual(len(selection.entries), 1)
        self.assertEqual(selection.entries[0].speaker_name, "Alice")
        self.buffer.mark_consumed(selection)

        later = make_event("3", name="Carol")
        next_call = make_event("4", name="Dave")
        self.buffer.capture(later, UniMessage.text("new ambient message"))
        next_selection = self.buffer.select_before(
            next_call,
            UniMessage.text("call again"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )

        self.assertEqual(len(next_selection.entries), 1)
        rendered = group_context.format_recent_group_context(next_selection.entries)
        self.assertIn("new ambient message", rendered)
        self.assertNotIn("first ambient message", rendered)

    def test_empty_at_trigger_still_creates_a_consumption_boundary(self):
        ambient = make_event("1")
        current = make_event("2")
        self.buffer.capture(ambient, UniMessage.text("ambient"))

        selection = self.buffer.select_before(
            current,
            UniMessage([At("user", "999")]),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )

        self.assertEqual(len(selection.entries), 1)
        self.assertGreater(selection.current_sequence, selection.entries[0].sequence)

    def test_concurrent_bot_calls_are_not_replayed_as_ambient_context(self):
        ambient = make_event("1")
        first_call = make_event("2")
        second_call = make_event("3")
        self.buffer.capture(ambient, UniMessage.text("ambient"))
        first = self.buffer.select_before(
            first_call,
            UniMessage.text("first bot call"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )
        self.buffer.begin_chat(first)

        second = self.buffer.select_before(
            second_call,
            UniMessage.text("second bot call"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )
        rendered = group_context.format_recent_group_context(second.entries)

        self.assertIn("ambient", rendered)
        self.assertNotIn("first bot call", rendered)

        self.buffer.cancel_chat(first)
        third_call = make_event("4")
        third = self.buffer.select_before(
            third_call,
            UniMessage.text("third bot call"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )
        self.assertIn(
            "first bot call",
            group_context.format_recent_group_context(third.entries),
        )

    def test_time_and_count_limits_are_both_applied(self):
        old = make_event("1")
        self.buffer.capture(old, UniMessage.text("too old"))
        self.clock.value += 700
        for index in range(4):
            self.buffer.capture(
                make_event(str(index + 2)),
                UniMessage.text(f"recent-{index}"),
            )
        current = make_event("9")

        selection = self.buffer.select_before(
            current,
            UniMessage.text("current"),
            max_messages=2,
            max_age_seconds=600,
            max_chars=6000,
        )

        rendered = group_context.format_recent_group_context(selection.entries)
        self.assertEqual(len(selection.entries), 2)
        self.assertNotIn("too old", rendered)
        self.assertNotIn("recent-1", rendered)
        self.assertIn("recent-2", rendered)
        self.assertIn("recent-3", rendered)

    def test_successful_reply_consumes_messages_that_arrived_while_waiting(self):
        before = make_event("1")
        current = make_event("2")
        during = make_event("3")
        self.buffer.capture(before, UniMessage.text("before call"))
        selection = self.buffer.select_before(
            current,
            UniMessage.text("current call"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )
        self.buffer.begin_chat(selection)
        self.buffer.capture(during, UniMessage.text("while waiting"))

        self.buffer.mark_replied(selection)
        later = self.buffer.select_before(
            make_event("4"),
            UniMessage.text("later call"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )

        self.assertEqual(later.entries, ())

    def test_images_keep_their_message_position_and_attachment_name(self):
        event = make_event("1", name="Alice")
        message = UniMessage([
            Text("before"),
            Image(url="https://example.com/cat.png", name="cat.png"),
            Text("after"),
        ])
        self.buffer.capture(event, message)
        current = make_event("2")
        selection = self.buffer.select_before(
            current,
            UniMessage.text("current"),
            max_messages=10,
            max_age_seconds=600,
            max_chars=6000,
        )
        entry = selection.entries[0]

        rendered = group_context.format_recent_group_context(
            selection.entries,
            attachment_names={(entry.sequence, 1): "group-context-1-image-1.png"},
        )

        self.assertLess(rendered.index("before"), rendered.index("group-context-1-image-1.png"))
        self.assertLess(rendered.index("group-context-1-image-1.png"), rendered.index("after"))
        self.assertEqual(entry.images[0].source.url, "https://example.com/cat.png")

    def test_private_messages_are_not_buffered(self):
        event = make_event("1")
        del event.group_id

        self.assertIsNone(self.buffer.capture(event, UniMessage.text("private")))
