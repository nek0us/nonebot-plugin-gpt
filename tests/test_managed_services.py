import asyncio
import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
services = importlib.import_module("nonebot_plugin_gpt.managed_services")


class ManagedServicesTests(unittest.TestCase):
    def test_pid_file_service_only_accepts_configured_name(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "service.pid"
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
            registry = services.ManagedServiceRegistry.from_config([{
                "name": "bot",
                "kind": "pid_file",
                "pid_file": str(pid_file),
            }])

            self.assertEqual(registry.process_names, ("bot",))
            self.assertIn("运行中", registry.process_status("bot"))
            self.assertIn("未找到", registry.process_status("arbitrary"))

    def test_invalid_or_duplicate_config_entries_are_ignored(self):
        registry = services.ManagedServiceRegistry.from_config([
            {"name": "bad", "kind": "tcp", "host": "127.0.0.1", "port": 0},
            {"name": "one", "kind": "pid_file", "pid_file": "/tmp/one.pid"},
            {"name": "one", "kind": "tcp", "host": "127.0.0.1", "port": 80},
        ])

        self.assertEqual(registry.process_names, ("one",))
        self.assertEqual(registry.tcp_names, ())
