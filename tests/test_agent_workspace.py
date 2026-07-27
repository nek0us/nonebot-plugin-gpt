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

    def test_workspace_project_file_operations_stay_inside_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = AgentWorkspace(Path(temporary))
            workspace.make_directory("project/assets")
            workspace.write_text("project/readme.md", "title\nTODO: first\n")

            self.assertIn("目录：project", workspace.describe_path("project"))
            self.assertIn("TODO: first", workspace.search_text("TODO", "project"))
            self.assertIn("已追加", workspace.append_text("project/readme.md", "TODO: second\n"))
            self.assertIn("2 处", workspace.replace_text("project/readme.md", "TODO", "DONE"))
            self.assertIn("已复制", workspace.copy_file("project/readme.md", "project/assets/copy.md"))
            self.assertIn("已移动", workspace.move_file("project/assets/copy.md", "project/final.md"))
            self.assertIn("已删除", workspace.delete_file("project/final.md"))
            self.assertIn("DONE: first", workspace.read_text("project/readme.md"))

    def test_workspace_rejects_overwrite_and_directory_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = AgentWorkspace(Path(temporary))
            workspace.write_text("source.txt", "source")
            workspace.write_text("target.txt", "target")
            workspace.make_directory("folder")

            with self.assertRaises(WorkspaceError):
                workspace.copy_file("source.txt", "target.txt")
            with self.assertRaises(WorkspaceError):
                workspace.delete_file("folder")
            with self.assertRaises(WorkspaceError):
                workspace.search_text("anything", "source.txt")
