import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "command_compat.py"
SPEC = importlib.util.spec_from_file_location("command_compat", MODULE_PATH)
assert SPEC and SPEC.loader
command_compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command_compat)


class LegacyCommandTest(unittest.TestCase):
    def test_alias_keeps_following_argument(self):
        command = command_compat.build_legacy_command("backloop", {"回到过去"})

        result = command.parse("回到过去 3")

        self.assertTrue(result.matched)
        self.assertEqual(result.main_args["argument"], "3")
