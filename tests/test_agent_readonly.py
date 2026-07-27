import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "agent_readonly.py"
SPEC = importlib.util.spec_from_file_location("agent_readonly", MODULE_PATH)
assert SPEC and SPEC.loader
agent_readonly = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent_readonly
SPEC.loader.exec_module(agent_readonly)
AgentReadonlyRoots = agent_readonly.AgentReadonlyRoots
ReadonlySourceError = agent_readonly.ReadonlySourceError


class AgentReadonlyRootsTests(unittest.TestCase):
    def test_searches_logs_then_reads_the_matching_source_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "logs"
            source = root / "source"
            logs.mkdir()
            source.mkdir()
            (logs / "bot.log").write_text(
                "booting\n"
                "2026-07-27 ERROR worker failed: AuthenticationExpired\n"
                "retry queued\n",
                encoding="utf-8",
            )
            (source / "session.py").write_text(
                "def refresh():\n"
                "    raise AuthenticationExpired()\n",
                encoding="utf-8",
            )
            roots = AgentReadonlyRoots([
                {"name": "运行日志", "path": logs},
                {"name": "核心源码", "path": source},
            ])

            log_search = roots.search_text({"根目录": "运行日志", "文本": "AuthenticationExpired"})
            source_search = roots.search_text({"根目录": "核心源码", "文本": "AuthenticationExpired"})
            excerpt = roots.read_excerpt({"根目录": "运行日志", "文件": "bot.log", "起始行": "2", "行数": "1"})

            self.assertIn("bot.log:2", log_search)
            self.assertIn("session.py:2", source_search)
            self.assertIn("2: 2026-07-27 ERROR", excerpt)

    def test_reads_large_log_tail_without_reading_the_whole_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            logs = Path(temporary) / "logs"
            logs.mkdir()
            (logs / "large.log").write_text(
                "old line\n" * 100_000 + "ERROR final failure\n",
                encoding="utf-8",
            )
            roots = AgentReadonlyRoots([{"name": "运行日志", "path": logs}])

            tail = roots.read_tail({"根目录": "运行日志", "文件": "large.log", "行数": "3"})

            self.assertIn("ERROR final failure", tail)
            self.assertNotIn("old line\nold line\nold line\nold line\nold line", tail)

    def test_rejects_unknown_roots_and_paths_outside_the_named_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "logs"
            logs.mkdir()
            (logs / "bot.log").write_text("hello", encoding="utf-8")
            roots = AgentReadonlyRoots([{"name": "运行日志", "path": logs}])

            with self.assertRaises(ReadonlySourceError):
                roots.read_excerpt({"根目录": "未知", "文件": "bot.log"})
            with self.assertRaises(ReadonlySourceError):
                roots.read_excerpt({"根目录": "运行日志", "文件": "../secret.txt"})
