import importlib.util
import tempfile
import unittest
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "chat_images.py"
_SPEC = importlib.util.spec_from_file_location("nonebot_plugin_gpt_chat_images", _MODULE_PATH)
assert _SPEC and _SPEC.loader
chat_images = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(chat_images)


class ChatImageTests(unittest.TestCase):
    def test_native_template_is_a_narrow_vertical_card(self):
        html = chat_images.build_chat_html("# 标题\n\n- 第一项", template="native")

        self.assertIn("width: 680px", html)
        self.assertIn("--gpt-image-font-scale: 1.00", html)
        self.assertIn("#8a72d6", html)
        self.assertIn("<h1>标题</h1>", html)
        self.assertIn("<li>第一项</li>", html)

    def test_off_template_uses_monochrome_reading_style(self):
        html = chat_images.build_chat_html("## 标题", template="off")

        self.assertIn("background: #ffffff", html)
        self.assertIn("border-left: 4px solid #333333", html)

    def test_builtin_template_accepts_font_scale(self):
        html = chat_images.build_chat_html("你好", template="native", font_scale=1.15)

        self.assertIn("--gpt-image-font-scale: 1.15", html)

    def test_custom_template_requires_and_replaces_content_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.html"
            path.write_text("<main>{{ content }}</main>", encoding="utf-8")
            html = chat_images.build_chat_html("你好", template=str(path))

        self.assertEqual(html, "<main><p>你好</p></main>")

    def test_custom_template_without_placeholder_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.html"
            path.write_text("<main>missing</main>", encoding="utf-8")
            with self.assertRaises(ValueError):
                chat_images.build_chat_html("你好", template=str(path))
