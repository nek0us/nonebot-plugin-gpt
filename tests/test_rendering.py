import importlib.util
import unittest
from pathlib import Path

from ChatGPTWeb import ChatContent, CodeBlock, RichContentItem


_MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "rendering.py"
_SPEC = importlib.util.spec_from_file_location("nonebot_plugin_gpt_rendering", _MODULE_PATH)
assert _SPEC and _SPEC.loader
rendering = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rendering)


class RenderingTests(unittest.TestCase):
    def test_plain_text_is_used_when_markdown_is_not_supported(self):
        content = ChatContent(markdown="[OpenAI](https://openai.com)", plain_text="OpenAI (https://openai.com)")

        self.assertEqual(rendering.text_for_platform(content, False), "OpenAI (https://openai.com)")
        self.assertEqual(rendering.text_for_platform(content, True), "[OpenAI](https://openai.com)")

    def test_only_complex_content_requires_markdown_image_fallback(self):
        self.assertFalse(rendering.should_render_markdown_image(ChatContent(markdown="A short answer.")))
        self.assertTrue(rendering.should_render_markdown_image(ChatContent(markdown="# Heading")))
        self.assertTrue(rendering.should_render_markdown_image(
            ChatContent(markdown="code", code_blocks=[CodeBlock(language="python", code="print()")])
        ))
        self.assertTrue(rendering.should_render_markdown_image(
            ChatContent(markdown="weather", rich_items=[RichContentItem(kind="aggregate_result", payload={})])
        ))


if __name__ == "__main__":
    unittest.main()
