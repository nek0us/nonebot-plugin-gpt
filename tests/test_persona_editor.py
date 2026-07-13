import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
persona_editor = importlib.import_module("nonebot_plugin_gpt.persona_editor")


class PersonaEditorTests(unittest.TestCase):
    def test_name_validation_rejects_duplicates_and_banned_words(self):
        with self.assertRaises(persona_editor.PersonaValidationError):
            persona_editor.validate_name("船长", {"船长": {}}, [])
        with self.assertRaises(persona_editor.PersonaValidationError):
            persona_editor.validate_name("坏词船长", {}, ["坏词"])

    def test_visibility_and_r18_parsing(self):
        self.assertTrue(persona_editor.parse_r18("是"))
        self.assertEqual(persona_editor.parse_visibility("私有", "alice"), "alice")
        self.assertEqual(persona_editor.parse_visibility("公开", "alice"), "")
