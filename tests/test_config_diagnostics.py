import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
diagnostics = importlib.import_module("nonebot_plugin_gpt.config_diagnostics")


class ConfigDiagnosticsTests(unittest.TestCase):
    def test_conflicting_gpt_values_report_lines_and_effective_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.prod"
            path.write_text(
                "gpt_free_image=true\n"
                "NICKNAME=['bot']\n"
                "gpt_free_image=false\n",
                encoding="utf-8",
            )

            conflicts = diagnostics.find_conflicting_gpt_settings(path)

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["key"], "gpt_free_image")
        self.assertEqual(conflicts[0]["effective_line"], 3)
        self.assertEqual(conflicts[0]["effective_value"], "false")
        self.assertEqual(
            [item["line"] for item in conflicts[0]["assignments"]],
            [1, 3],
        )

    def test_sensitive_duplicate_values_are_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "gpt_core_api_key=first\n"
                "gpt_core_api_key=second\n",
                encoding="utf-8",
            )

            conflict = diagnostics.find_conflicting_gpt_settings(path)[0]

        self.assertEqual(conflict["effective_value"], "<已隐藏>")
        self.assertNotIn("second", str(conflict))

    def test_later_env_file_override_is_reported_as_effective(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / ".env"
            production = Path(directory) / ".env.prod"
            base.write_text("gpt_free_image=true\n", encoding="utf-8")
            production.write_text("gpt_free_image=false\n", encoding="utf-8")

            conflict = diagnostics.find_conflicting_gpt_settings(
                (base, production)
            )[0]

        self.assertEqual(conflict["effective_file"], str(production.resolve()))
        self.assertEqual(conflict["effective_line"], 1)
        self.assertEqual(conflict["effective_value"], "false")
        self.assertEqual(
            [item["file"] for item in conflict["assignments"]],
            [str(base.resolve()), str(production.resolve())],
        )
