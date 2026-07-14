import importlib
import os
import sys
import types
import unittest
from pathlib import Path

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
