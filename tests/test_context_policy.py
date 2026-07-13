import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "context_policy.py"
SPEC = importlib.util.spec_from_file_location("context_policy", MODULE_PATH)
assert SPEC and SPEC.loader
context_policy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context_policy
SPEC.loader.exec_module(context_policy)


class ContextPolicyTests(unittest.TestCase):
    def test_only_persona_sessions_with_explicit_window_can_compact(self):
        decision = context_policy.decide_context_maintenance(
            estimated_tokens=15_000,
            context_window_tokens=20_000,
            policy=context_policy.ContextPolicy(),
            has_persona=True,
        )

        self.assertTrue(decision.compact)
        self.assertFalse(context_policy.decide_context_maintenance(
            estimated_tokens=15_000,
            context_window_tokens=None,
            policy=context_policy.ContextPolicy(),
            has_persona=True,
        ).compact)
        self.assertFalse(context_policy.decide_context_maintenance(
            estimated_tokens=15_000,
            context_window_tokens=20_000,
            policy=context_policy.ContextPolicy(),
            has_persona=False,
        ).compact)

    def test_restart_prompt_keeps_persona_summary_and_current_message(self):
        prompt = context_policy.build_restart_prompt("保持冷静", "已经到达港口", "接下来去哪？")

        self.assertIn("保持冷静", prompt)
        self.assertIn("已经到达港口", prompt)
        self.assertIn("接下来去哪？", prompt)
