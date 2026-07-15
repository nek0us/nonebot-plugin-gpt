import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
access_views = importlib.import_module("nonebot_plugin_gpt.access_views")


class AccessViewTests(unittest.TestCase):
    def test_parse_session_target_and_paid_marker(self):
        identifier, paid = access_views.parse_access_target("plus chat-1")

        self.assertEqual(identifier, "chat-1")
        self.assertTrue(paid)

    def test_parse_access_target_uses_current_session_by_default(self):
        identifier, paid = access_views.parse_access_target(
            "plus",
            default_target="telegram:private:1",
        )

        self.assertEqual(identifier, "telegram:private:1")
        self.assertTrue(paid)

    def test_format_whitelist_marks_paid_targets(self):
        text = access_views.format_whitelist(
            {"version": 2, "sessions": ["telegram:private:1"]},
            {"status": True, "telegram:private:1": "gpt-5"},
        )

        self.assertIn("会话：telegram:private:1，Plus", text)

    def test_format_whitelist_keeps_legacy_entries_visible(self):
        text = access_views.format_whitelist(
            {"version": 2, "sessions": [], "legacy": {"group": ["123"]}},
            {"status": True},
        )

        self.assertIn("旧版group：123", text)

    def test_format_whitelist_shows_personal_grants(self):
        text = access_views.format_whitelist(
            {"version": 2, "sessions": [], "users": ["onebot.v11:user:42"]},
            {"status": True},
        )

        self.assertIn("个人：onebot.v11:user:42", text)
