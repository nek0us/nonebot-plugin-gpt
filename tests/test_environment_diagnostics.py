import importlib
import sys
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
diagnostics = importlib.import_module("nonebot_plugin_gpt.environment_diagnostics")


class EnvironmentDiagnosticsTests(unittest.TestCase):
    def test_collector_exposes_portable_baseline_fields(self):
        result = diagnostics.collect_environment_diagnostics()

        self.assertTrue(result["system"])
        self.assertIn("disk_total", result)
        self.assertIn("memory_total", result)
        self.assertIn("memory_usage_percent", result)
        self.assertIn("cpu_count", result)

    def test_formatter_marks_missing_platform_data_as_unavailable(self):
        text = diagnostics.format_environment_diagnostics({
            "system": "TestOS",
            "release": "1.0",
            "machine": "x64",
            "python": "3.x",
            "cpu_count": None,
            "memory_total": None,
            "memory_available": None,
            "memory_used": None,
            "memory_usage_percent": None,
            "disk_target": "/",
            "disk_total": None,
            "disk_free": None,
            "load_average": None,
        })

        self.assertIn("本机环境诊断", text)
        self.assertIn("不可用", text)
        self.assertIn("不适用", text)
