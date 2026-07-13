import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
persona_views = importlib.import_module("nonebot_plugin_gpt.persona_views")


class Personality:
    init_list = [{"name": "船长"}, {"name": "秘密"}]

    def get_value_by_name(self, name):
        return {"船长": "你是一位船长", "秘密": "仅限本人"}.get(name, "")


class PersonaViewTests(unittest.TestCase):
    def test_list_contains_visibility_and_r18_markers(self):
        message = persona_views.list_personas(Personality(), {
            "船长": {"r18": False, "open": ""},
            "秘密": {"r18": True, "open": "alice"},
        })

        self.assertIn("船长 (普通, 公开)", message.extract_plain_text())
        self.assertIn("秘密 (R18, 私有)", message.extract_plain_text())

    def test_private_persona_is_not_exposed_to_other_users(self):
        message = persona_views.show_persona(
            Personality(),
            {"秘密": {"open": "alice"}},
            "秘密",
            "bob",
        )

        self.assertIn("不能查看", message.extract_plain_text())
