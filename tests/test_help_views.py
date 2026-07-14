import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "help_views.py"
SPEC = importlib.util.spec_from_file_location("help_views", MODULE_PATH)
assert SPEC and SPEC.loader
help_views = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(help_views)


class HelpViewsTests(unittest.TestCase):
    def test_default_help_lists_main_topics(self):
        text = help_views.format_help()

        self.assertIn("会话", text)
        self.assertIn("人设", text)
        self.assertIn("GPT帮助 <主题>", text)

    def test_help_sections_are_selected_by_topic(self):
        self.assertIn("切换会话", help_views.format_help("会话"))
        self.assertIn("工作状态", help_views.format_help("管理"))
        self.assertIn("智能体 计划", help_views.format_help("agent"))

    def test_unknown_topic_is_explained(self):
        self.assertIn("可用主题", help_views.format_help("不存在"))
