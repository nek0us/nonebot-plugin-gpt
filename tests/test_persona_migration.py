import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
persona_migration = importlib.import_module("nonebot_plugin_gpt.persona_migration")


class PersonaMigrationTests(unittest.TestCase):
    def test_legacy_personas_are_merged_into_runtime_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            (data_dir / "personality").write_text(
                '{"name":"旧人设","value":"旧正文"}\n',
                encoding="utf-8",
            )
            target = data_dir / "chatgptweb" / "personas.json"
            target.parent.mkdir()
            target.write_text(
                json.dumps({
                    "version": 2,
                    "personas": [
                        {"name": "新", "value": "新正文"},
                        {"name": "", "value": "无效正文"},
                    ],
                }),
                encoding="utf-8",
            )

            values = persona_migration.migrate_legacy_personas(data_dir)

            self.assertEqual({item["name"] for item in values}, {"旧人设", "新"})
            stored = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(stored["version"], 2)
            self.assertEqual(len(stored["personas"]), 2)
