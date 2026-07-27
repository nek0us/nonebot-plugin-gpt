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

            result = scanner.scan({"扫描目录": str(root.resolve()), "最大深度": "2", "结果数量": "5"})

            self.assertIn("large", result)
            self.assertIn("4.0 KiB", result)
            self.assertLess(result.index("large"), result.index("small"))

    def test_scan_rejects_unconfigured_root_and_invalid_depth(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scanner = agent_filesystem.AgentFilesystemScanner([root])

            self.assertIn("不在管理员配置", scanner.validate({"扫描目录": str(root.parent), "最大深度": "2"}))
            self.assertIn("1 到", scanner.validate({"扫描目录": str(root.resolve()), "最大深度": "99"}))

    def test_named_root_hides_absolute_path_from_tool_parameter_choices(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scanner = agent_filesystem.AgentFilesystemScanner([{"name": "机器人目录", "path": str(root)}])

            self.assertEqual(scanner.root_choices, ("机器人目录",))
            self.assertEqual(scanner.validate({"扫描目录": "机器人目录"}), "")

    def test_scan_can_rank_files_instead_of_directories(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "logs").mkdir()
            (root / "logs" / "small.log").write_bytes(b"a" * 128)
            (root / "logs" / "large.log").write_bytes(b"a" * 4096)
            scanner = agent_filesystem.AgentFilesystemScanner([{"name": "机器人目录", "path": root}])

            result = scanner.scan({
                "扫描目录": "机器人目录",
                "统计对象": "文件",
                "最大深度": "2",
                "结果数量": "5",
            })

            self.assertIn("占用较大的文件", result)
            self.assertLess(result.index("logs/large.log"), result.index("logs/small.log"))
