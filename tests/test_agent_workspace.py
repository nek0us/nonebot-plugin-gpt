import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "agent_workspace.py"
SPEC = importlib.util.spec_from_file_location("agent_workspace", MODULE_PATH)
assert SPEC and SPEC.loader
agent_workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_workspace)
AgentWorkspace = agent_workspace.AgentWorkspace
WorkspaceError = agent_workspace.WorkspaceError


class AgentWorkspaceTests(unittest.TestCase):
    def test_lists_reads_and_writes_files_inside_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = AgentWorkspace(Path(temporary))

            written = workspace.write_text("notes/hello.txt", "hello from agent")

            self.assertIn("notes/hello.txt", written)
            self.assertIn("notes/hello.txt", workspace.list_files("notes"))
            self.assertIn("hello from agent", workspace.read_text("notes/hello.txt"))

    def test_rejects_paths_outside_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = AgentWorkspace(Path(temporary))

            with self.assertRaises(WorkspaceError):
                workspace.read_text("../outside.txt")
            with self.assertRaises(WorkspaceError):
                workspace.write_text("C:/outside.txt", "blocked")

    def test_rejects_non_utf8_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = AgentWorkspace(root)
            (root / "binary.bin").write_bytes(b"\xff\xfe")
            (root / "large.txt").write_text("x" * (65 * 1024), encoding="utf-8")

            with self.assertRaises(WorkspaceError):
                workspace.read_text("binary.bin")
            with self.assertRaises(WorkspaceError):
                workspace.read_text("large.txt")
