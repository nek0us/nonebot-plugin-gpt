import asyncio
import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch
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

    def test_restart_is_only_available_for_preconfigured_command(self):
        registry = services.ManagedServiceRegistry.from_config([{
            "name": "bot",
            "kind": "pid_file",
            "pid_file": "/tmp/bot.pid",
            "restart_command": ["restart-bot"],
        }])

        self.assertEqual(registry.restart_names, ("bot",))
        self.assertIn("未找到", asyncio.run(registry.restart("unknown")))

    def test_restart_uses_configured_argument_array_without_shell(self):
        registry = services.ManagedServiceRegistry.from_config([{
            "name": "bot",
            "kind": "pid_file",
            "pid_file": "/tmp/bot.pid",
            "restart_command": ["restart-bot", "--graceful"],
        }])
        calls = []

        class _Process:
            returncode = 0

            async def wait(self):
                return 0

        async def create_process(*args, **kwargs):
            calls.append((args, kwargs))
            return _Process()

        with (
            patch.object(services.asyncio, "create_subprocess_exec", side_effect=create_process),
            patch.object(services.asyncio, "sleep", new=AsyncMock()),
            patch.object(registry, "process_status", return_value="服务 bot：运行中（PID 1）。"),
        ):
            result = asyncio.run(registry.restart("bot"))

        self.assertIn("已提交", result)
        self.assertIn("复检结果：运行中", result)
        self.assertEqual(calls[0][0], ("restart-bot", "--graceful"))
        self.assertNotIn("shell", calls[0][1])
