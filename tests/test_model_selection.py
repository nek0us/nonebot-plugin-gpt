import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
model_selection = importlib.import_module("nonebot_plugin_gpt.model_selection")


class ModelSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_whitelisted_model_is_returned_with_paid_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plus_status.json"
            path.write_text('{"status": true, "group-1": "gpt-5"}', encoding="utf-8")

            async def get_identifier(_event):
                return "group-1"

            with (
                patch.object(model_selection, "_plusstatus_path", return_value=path),
                patch.object(model_selection, "_legacy_identifier", get_identifier),
                patch.object(model_selection, "_force_upgrade_model", return_value=True),
                patch.object(model_selection, "_upgrade_free_model", side_effect=lambda value: value),
            ):
                model, prefer_paid_account = await model_selection.select_model(object())

        self.assertEqual(model, "gpt-5")
        self.assertTrue(prefer_paid_account)

    async def test_explicit_paid_preference_survives_without_whitelist_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plus_status.json"
            path.write_text('{"status": true}', encoding="utf-8")

            async def get_identifier(_event):
                return "group-1"

            with (
                patch.object(model_selection, "_plusstatus_path", return_value=path),
                patch.object(model_selection, "_legacy_identifier", get_identifier),
            ):
                model, prefer_paid_account = await model_selection.select_model(
                    object(),
                    prefer_paid_account=True,
                )

        self.assertEqual(model, "auto")
        self.assertTrue(prefer_paid_account)
