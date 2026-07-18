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
agent_sandbox = importlib.import_module("nonebot_plugin_gpt.agent_sandbox")
agent_workspace = importlib.import_module("nonebot_plugin_gpt.agent_workspace")
agent_web = importlib.import_module("nonebot_plugin_gpt.agent_web")


class AgentSandboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_backend_executes_only_workspace_python_file(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = agent_workspace.AgentWorkspace(root)
            workspace.write_text("scripts/hello.py", "print('hello from sandbox')")
            sandbox = agent_sandbox.WorkspaceSandbox(workspace, backend="local", timeout_seconds=10)

            output = await sandbox.run("scripts/hello.py")

            self.assertIn("脚本退出码：0", output)
            self.assertIn("hello from sandbox", output)

    async def test_disabled_backend_and_outside_script_are_rejected(self):
        with TemporaryDirectory() as temporary:
            workspace = agent_workspace.AgentWorkspace(Path(temporary))
            disabled = agent_sandbox.WorkspaceSandbox(workspace)
            with self.assertRaises(agent_sandbox.SandboxError):
                disabled.validate("script.py")

            sandbox = agent_sandbox.WorkspaceSandbox(workspace, backend="local")
            with self.assertRaises(agent_sandbox.SandboxError):
                sandbox.validate("../outside.py")

    async def test_web_renderer_rejects_remote_or_active_html_before_rendering(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = agent_workspace.AgentWorkspace(root)
            workspace.write_text("unsafe.html", "<script>alert(1)</script>")
            renderer = agent_web.WorkspaceWebRenderer(workspace)

            with self.assertRaises(agent_web.WebRenderError):
                await renderer.render("unsafe.html", "unsafe.png")

            workspace.write_text("remote-style.html", "<style>body{background:url(https://example.com/a.png)}</style>")
            with self.assertRaises(agent_web.WebRenderError):
                await renderer.render("remote-style.html", "remote-style.png")
