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
agent_commands = importlib.import_module("nonebot_plugin_gpt.agent_commands")


class AgentCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_rejects_shell_string_and_workdir_escape(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = agent_commands.CommandRunner(working_directory=root)

            with self.assertRaises(agent_commands.CommandValidationError):
                runner.parse({"程序": "", "参数": "[]"})
            with self.assertRaises(agent_commands.CommandValidationError):
                runner.parse({"程序": "python", "参数": "not-json"})
            with self.assertRaises(agent_commands.CommandValidationError):
                runner.parse({"程序": "python", "参数": "[]", "工作目录": str(root.parent)})

    async def test_runner_uses_argv_and_returns_bounded_result(self):
        runner = agent_commands.CommandRunner(default_timeout_seconds=5)
        result = await runner.run({
            "程序": sys.executable,
            "参数": '["-c", "print(\'agent-ok\')"]',
        })

        self.assertIn("命令退出码：0", result)
        self.assertIn("agent-ok", result)

    async def test_runner_kills_timed_out_process(self):
        runner = agent_commands.CommandRunner(default_timeout_seconds=1)
        result = await runner.run({
            "程序": sys.executable,
            "参数": '["-c", "import time; time.sleep(3)"]',
        })

        self.assertIn("命令超时，已终止", result)
