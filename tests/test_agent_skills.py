import importlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ChatGPTWeb import AgentDecision, AgentState, AgentTurn


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
agent_commands = importlib.import_module("nonebot_plugin_gpt.agent_commands")
agent_runtime = importlib.import_module("nonebot_plugin_gpt.agent_runtime")
agent_skills = importlib.import_module("nonebot_plugin_gpt.agent_skills")


class _Service:
    async def get_account_status(self):
        return {"accounts": []}

    async def get_model_catalog(self, fetch_remote=False):
        return {"local": {"free": {}, "plus": {}}}


class _AgentService:
    def __init__(self, decisions):
        self._decisions = list(decisions)

    async def turn(self, task, tools, *, state=None, tool_result=None, model="auto"):
        return AgentTurn(True, AgentState("conversation", "message", model), self._decisions.pop(0))


class AgentSkillTests(unittest.IsolatedAsyncioTestCase):
    def test_skill_uses_only_declared_template_variables(self):
        runner = agent_commands.CommandRunner()
        skill = agent_skills.DeclarativeCommandSkill.from_config({
            "name": "问候",
            "description": "输出固定前缀与受限名称",
            "program": "echo",
            "arguments": ["hello", "{名称}"],
            "parameters": [{"name": "名称", "description": "已审核的目标名称", "choices": ["bot", "admin"]}],
        }, runner)

        self.assertEqual(skill.validate({"名称": "admin"}), "")
        self.assertIn("候选值", skill.validate({"名称": "other"}))
        self.assertIn("命令选项", skill.validate({"名称": "--danger"}))
        self.assertEqual(skill.command_arguments({"名称": "bot"})["参数"], '["hello", "bot"]')

    def test_optional_template_variable_can_be_omitted(self):
        runner = agent_commands.CommandRunner()
        skill = agent_skills.DeclarativeCommandSkill.from_config({
            "name": "可选参数",
            "description": "验证可选变量",
            "program": "echo",
            "arguments": ["prefix-{备注}"],
            "parameters": [{"name": "备注", "description": "可选备注", "required": False}],
        }, runner)

        self.assertEqual(skill.validate({}), "")
        self.assertEqual(skill.command_arguments({})["参数"], '["prefix-"]')

    def test_skill_rejects_undeclared_template_variable(self):
        runner = agent_commands.CommandRunner()
        with self.assertRaises(agent_skills.AgentSkillError):
            agent_skills.DeclarativeCommandSkill.from_config({
                "name": "错误技能",
                "description": "不应通过",
                "program": "echo",
                "arguments": ["{未知}"],
            }, runner)

    def test_local_skill_file_loads_and_reports_invalid_sources(self):
        runner = agent_commands.CommandRunner()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "skills.json"
            source.write_text('[{"name":"文件技能","description":"来自本地文件","program":"echo","arguments":["ok"]}]', encoding="utf-8")

            result = agent_skills.load_command_skill_sources([], [source, root / "missing.json"], runner)

            self.assertEqual([skill.name for skill in result.skills], ["文件技能"])
            self.assertEqual(len(result.issues), 1)
            self.assertIn("不存在", result.issues[0])

    async def test_configured_skill_is_model_selected_and_requires_confirmation(self):
        runner = agent_commands.CommandRunner()
        skill = agent_skills.DeclarativeCommandSkill.from_config({
            "name": "测试输出",
            "description": "输出受控测试文本",
            "program": sys.executable,
            "arguments": ["-c", "print('skill-ok')"],
        }, runner)
        service = _AgentService([
            AgentDecision("tool_call", tool="技能：测试输出", arguments={}),
            AgentDecision("final", answer="技能执行完成。"),
        ])
        runtime = agent_runtime.create_agent_runtime(
            _Service(),
            agent_service=service,
            command_runner=runner,
            command_skills=(skill,),
            token_factory=iter(("confirm", "next")).__next__,
        )

        pending = await runtime.execute("运行测试输出", operator_id="admin", scope_id="private:1")
        completed = await runtime.execute("确认 confirm", operator_id="admin", scope_id="private:1")

        self.assertIn("技能：测试输出", pending)
        self.assertIn("风险提示", pending)
        self.assertEqual(completed, "技能执行完成。")
