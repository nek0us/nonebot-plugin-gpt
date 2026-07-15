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


class ContextlessEvent:
    def get_user_id(self):
        raise ValueError("Event has no context!")

    def get_session_id(self):
        raise ValueError("Event has no context!")


class CheckRuleTests(unittest.IsolatedAsyncioTestCase):
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
