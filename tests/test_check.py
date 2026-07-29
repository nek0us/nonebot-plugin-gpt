import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import nonebot


os.environ["ENVIRONMENT"] = "test"
nonebot.init(_env_file=[])

PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
check = importlib.import_module("nonebot_plugin_gpt.check")
Config = importlib.import_module("nonebot_plugin_gpt.config").Config


class ContextlessEvent:
    def get_user_id(self):
        raise ValueError("Event has no context!")

    def get_session_id(self):
        raise ValueError("Event has no context!")


class AddressedEvent:
    def __init__(self, *, to_me: bool, text: str = ""):
        self._to_me = to_me
        self._text = text
        self.group_id = "100"

    def get_user_id(self):
        return "42"

    def get_session_id(self):
        return "group_100_42"

    def get_plaintext(self):
        return self._text

    def is_tome(self):
        return self._to_me


AddressedEvent.__module__ = "nonebot.adapters.onebot.v11.event"


class NoticeEvent:
    def get_user_id(self):
        return "42"

    def get_plaintext(self):
        raise ValueError("Event has no message!")

    def get_message(self):
        raise ValueError("Event has no message!")

    def is_tome(self):
        return False


NoticeEvent.__module__ = "nonebot.adapters.onebot.v11.event"


class CheckRuleTests(unittest.IsolatedAsyncioTestCase):
    def test_account_scheduler_config_accepts_balanced_window(self):
        config = Config(
            gpt_session=[],
            gpt_chat_rate_limit_cooldown_seconds=7200,
            gpt_account_selection_strategy="usage_balanced",
            gpt_account_selection_window_seconds=3600,
        )

        self.assertEqual(config.gpt_chat_rate_limit_cooldown_seconds, 7200)
        self.assertEqual(config.gpt_account_selection_strategy, "usage_balanced")
        self.assertEqual(config.gpt_account_selection_window_seconds, 3600)

    def test_remote_core_mode_does_not_require_local_sessions(self):
        config = Config(
            gpt_core_mode="remote",
            gpt_core_base_url="http://127.0.0.1:8000/v1/",
            gpt_core_api_key="cwk_remote_test_key",
            gpt_session=[{"email": "legacy@example.com"}],
        )

        self.assertEqual(config.gpt_core_base_url, "http://127.0.0.1:8000/v1")
        self.assertEqual(config.gpt_session, [])

    async def test_contextless_event_is_ignored_by_all_access_rules(self):
        event = ContextlessEvent()

        self.assertIsNone(check.get_event_user_id(event))
        self.assertEqual(check.get_access_session_id(event), "")
        self.assertEqual(check.get_participant_key(event), "")
        self.assertFalse(await check.gpt_rule(event))
        self.assertFalse(await check.gpt_command_rule(event))
        self.assertFalse(await check.gpt_manage_rule(event))
        self.assertFalse(await check.gpt_superuser_rule(event))
        self.assertFalse(await check.plus_status(event))

    async def test_notice_event_is_ignored_without_accessing_its_message(self):
        event = NoticeEvent()

        self.assertEqual(check._event_plain_text(event), "")
        self.assertFalse(check._is_message_event(event))
        self.assertFalse(await check.gpt_rule(event))
        self.assertFalse(await check.gpt_command_rule(event))
        self.assertFalse(await check.gpt_manage_rule(event))
        self.assertFalse(await check.gpt_superuser_rule(event))
        self.assertFalse(await check.plus_status(event))

    async def test_chat_requires_a_mention_or_configured_name(self):
        with (
            patch.object(check.config_gpt, "gpt_white_list_mode", False),
            patch.object(check.config_gpt, "gpt_chat_start", ["猪咪"]),
            patch.object(check.config_nb, "nickname", ["小猪"]),
        ):
            self.assertFalse(await check.gpt_rule(AddressedEvent(to_me=False, text="你好")))
            self.assertTrue(await check.gpt_rule(AddressedEvent(to_me=True, text="你好")))
            self.assertTrue(await check.gpt_rule(AddressedEvent(to_me=False, text="猪咪 你好")))
            self.assertTrue(await check.gpt_rule(AddressedEvent(to_me=False, text="小猪你好")))

    async def test_commands_require_a_mention_or_configured_name(self):
        with (
            patch.object(check.config_gpt, "gpt_white_list_mode", False),
            patch.object(check.config_gpt, "gpt_chat_start", ["猪咪"]),
        ):
            self.assertFalse(await check.gpt_command_rule(AddressedEvent(to_me=False, text="初始化 人设")))
            self.assertTrue(await check.gpt_command_rule(AddressedEvent(to_me=True, text="初始化 人设")))
            self.assertTrue(await check.gpt_command_rule(AddressedEvent(to_me=False, text="猪咪 初始化 人设")))

    def test_legacy_private_whitelist_keeps_onebot_cross_group_behavior(self):
        class GroupEvent:
            group_id = "123"

            def get_user_id(self):
                return "42"

            def get_session_id(self):
                return "group_123_42"

        GroupEvent.__module__ = "nonebot.adapters.onebot.v11.event"

        whitelist = {"legacy": {"private": ["42"]}, "sessions": []}
        self.assertTrue(check._legacy_whitelist_matches(GroupEvent(), whitelist))

    def test_personal_whitelist_grants_all_scopes_on_the_same_adapter(self):
        class GroupEvent:
            group_id = "456"

            def get_user_id(self):
                return "42"

            def get_session_id(self):
                return "group_456_42"

        GroupEvent.__module__ = "nonebot.adapters.onebot.v11.event"
        whitelist = {
            "sessions": [],
            "users": ["onebot.v11:user:42"],
            "legacy": {},
        }
        with patch.object(check, "read_whitelist", return_value=whitelist):
            self.assertTrue(check.is_whitelisted(GroupEvent()))

        whitelist["users"] = ["satori:user:42"]
        with patch.object(check, "read_whitelist", return_value=whitelist):
            self.assertFalse(check.is_whitelisted(GroupEvent()))

    def test_personal_identity_keeps_satori_platforms_separate(self):
        class Login:
            platform = "telegram"

        class SatoriEvent:
            login = Login()

            def get_user_id(self):
                return "42"

            def get_session_id(self):
                return "chat-1"

        SatoriEvent.__module__ = "nonebot.adapters.satori.event"
        self.assertEqual(
            check.get_event_user_identity(SatoriEvent()),
            "satori:telegram:user:42",
        )
