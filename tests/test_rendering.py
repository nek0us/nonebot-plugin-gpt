import importlib.util
import sys
import unittest
from pathlib import Path

from ChatGPTWeb import ChatContent, ChatResult, CodeBlock, RichContentItem


_MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "rendering.py"
_SPEC = importlib.util.spec_from_file_location("nonebot_plugin_gpt_rendering", _MODULE_PATH)
assert _SPEC and _SPEC.loader
rendering = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = rendering
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

    def test_render_plan_keeps_model_usage_and_images(self):
        content = ChatContent(markdown="# Title", plain_text="Title")
        result = ChatResult(
            ok=True,
            text=content.markdown,
            conversation_id="conversation",
            message_id="message",
            used_model="gpt-5",
            image_urls=["https://example.invalid/image.png"],
            usage={"total_tokens": 42},
            content=content,
        )

        plan = rendering.build_render_plan(result)

        self.assertEqual(plan.text, "Title")
        self.assertTrue(plan.markdown_image_required)
        self.assertEqual(plan.model, "gpt-5")
        self.assertEqual(plan.usage["total_tokens"], 42)
        self.assertEqual(plan.image_urls, ["https://example.invalid/image.png"])


if __name__ == "__main__":
    unittest.main()
