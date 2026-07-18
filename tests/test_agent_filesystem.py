import importlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
agent_filesystem = importlib.import_module("nonebot_plugin_gpt.agent_filesystem")


class AgentFilesystemTests(unittest.TestCase):
    def test_scan_lists_largest_directories_without_following_links(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "large").mkdir()
            (root / "small").mkdir()
            (root / "large" / "payload.bin").write_bytes(b"a" * 4096)
            (root / "small" / "payload.bin").write_bytes(b"a" * 128)
            scanner = agent_filesystem.AgentFilesystemScanner([root])

            result = scanner.scan({"根目录": str(root.resolve()), "最大深度": "2", "结果数量": "5"})

            self.assertIn("large", result)
            self.assertIn("4.0 KiB", result)
            self.assertLess(result.index("large"), result.index("small"))

    def test_scan_rejects_unconfigured_root_and_invalid_depth(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scanner = agent_filesystem.AgentFilesystemScanner([root])

            self.assertIn("不在管理员配置", scanner.validate({"根目录": str(root.parent), "最大深度": "2"}))
            self.assertIn("1 到", scanner.validate({"根目录": str(root.resolve()), "最大深度": "99"}))
