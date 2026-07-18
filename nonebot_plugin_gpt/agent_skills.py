"""由管理员配置声明的受控系统技能。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

from .agent_commands import CommandRunner, CommandValidationError


class AgentSkillError(ValueError):
    """技能配置或模型提交的技能参数不符合安全约束。"""


MAX_SKILL_FILE_BYTES = 256 * 1024


@dataclass(frozen=True)
class AgentSkillParameter:
    name: str
    description: str
    required: bool = True
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeclarativeCommandSkill:
    """程序和 argv 结构由管理员固定，模型只能填写声明过的变量。"""

    name: str
    description: str
    program: str
    argument_templates: tuple[str, ...]
    parameters: tuple[AgentSkillParameter, ...]
    working_directory: str = ""
    timeout_seconds: int = 30

    @classmethod
    def from_config(cls, value: dict[str, Any], runner: CommandRunner) -> "DeclarativeCommandSkill":
        if not isinstance(value, dict):
            raise AgentSkillError("每个智能体技能必须是对象。")
        name = value.get("name", "")
        description = value.get("description", "")
        program = value.get("program", "")
        templates = value.get("arguments", [])
        if not all(isinstance(item, str) for item in (name, description, program)):
            raise AgentSkillError("技能名称、说明和程序必须是文本。")
        name = name.strip()
        description = description.strip()
        program = program.strip()
        if not name or len(name) > 64 or not description or len(description) > 1024:
            raise AgentSkillError("技能名称或说明为空，或长度超过限制。")
        if not isinstance(templates, list) or len(templates) > 64 or not all(isinstance(item, str) for item in templates):
            raise AgentSkillError(f"技能“{name}”的 arguments 必须是最多 64 项的字符串数组。")
        parameters = cls._parameters(value.get("parameters", []), name)
        declared = {parameter.name for parameter in parameters}
        for template in templates:
            for _, field_name, format_spec, conversion in Formatter().parse(template):
                if field_name is None:
                    continue
                if field_name not in declared or format_spec or conversion:
                    raise AgentSkillError(f"技能“{name}”包含未声明或不安全的参数占位符：{field_name}。")
        working_directory = value.get("working_directory", "")
        if not isinstance(working_directory, str):
            raise AgentSkillError(f"技能“{name}”的 working_directory 必须是文本。")
        timeout = value.get("timeout_seconds", 30)
        if not isinstance(timeout, int) or not 1 <= timeout <= 600:
            raise AgentSkillError(f"技能“{name}”的 timeout_seconds 必须在 1 到 600 之间。")
        skill = cls(name, description, program, tuple(templates), parameters, working_directory.strip(), timeout)
        try:
            runner.parse(skill.command_arguments({}))
        except (CommandValidationError, AgentSkillError) as error:
            if any("{" + item.name + "}" in template for item in templates for item in parameters):
                # 含变量的技能在首次真实调用时再做完整 argv 校验。
                return skill
            raise AgentSkillError(f"技能“{name}”的固定命令不安全：{error}") from error
        return skill

    @staticmethod
    def _parameters(value: Any, skill_name: str) -> tuple[AgentSkillParameter, ...]:
        if value is None:
            value = []
        if not isinstance(value, list) or len(value) > 16:
            raise AgentSkillError(f"技能“{skill_name}”的 parameters 必须是最多 16 项的数组。")
        result: list[AgentSkillParameter] = []
        names: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                raise AgentSkillError(f"技能“{skill_name}”的参数必须是对象。")
            name = item.get("name", "")
            description = item.get("description", "")
            required = item.get("required", True)
            choices = item.get("choices", [])
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 64:
                raise AgentSkillError(f"技能“{skill_name}”存在无效参数名。")
            if name in names or not isinstance(description, str) or not description.strip():
                raise AgentSkillError(f"技能“{skill_name}”存在重复参数或空参数说明。")
            if not isinstance(required, bool) or not isinstance(choices, list) or not all(isinstance(choice, str) for choice in choices):
                raise AgentSkillError(f"技能“{skill_name}”参数配置无效。")
            names.add(name)
            result.append(AgentSkillParameter(name, description.strip(), required, tuple(dict.fromkeys(choices))))
        return tuple(result)

    def validate(self, values: dict[str, str]) -> str:
        expected = {parameter.name: parameter for parameter in self.parameters}
        if set(values).difference(expected):
            return "技能参数包含未声明字段。"
        for parameter in self.parameters:
            value = values.get(parameter.name, "")
            if parameter.required and not value.strip():
                return f"技能参数“{parameter.name}”不能为空。"
            if not value:
                continue
            if "\x00" in value or len(value) > 2048:
                return f"技能参数“{parameter.name}”包含非法或过长内容。"
            if value.startswith("-") or value.startswith("/"):
                return f"技能参数“{parameter.name}”不能以命令选项开头。"
            if parameter.choices and value not in parameter.choices:
                return f"技能参数“{parameter.name}”不在管理员允许的候选值中。"
        try:
            self.command_arguments(values)
        except AgentSkillError as error:
            return str(error)
        return ""

    def command_arguments(self, values: dict[str, str]) -> dict[str, str]:
        error = self.validate_values_only(values)
        if error:
            raise AgentSkillError(error)
        format_values = {parameter.name: values.get(parameter.name, "") for parameter in self.parameters}
        try:
            arguments = [template.format(**format_values) for template in self.argument_templates]
        except KeyError as error:
            raise AgentSkillError(f"缺少技能参数：{error.args[0]}。") from error
        result = {
            "程序": self.program,
            "参数": json.dumps(arguments, ensure_ascii=False),
            "工作目录": self.working_directory,
            "超时秒数": str(self.timeout_seconds),
        }
        return result

    def validate_values_only(self, values: dict[str, str]) -> str:
        expected = {parameter.name: parameter for parameter in self.parameters}
        if set(values).difference(expected):
            return "技能参数包含未声明字段。"
        for parameter in self.parameters:
            value = values.get(parameter.name, "")
            if parameter.required and not value.strip():
                return f"技能参数“{parameter.name}”不能为空。"
            if not value:
                continue
            if "\x00" in value or len(value) > 2048:
                return f"技能参数“{parameter.name}”包含非法或过长内容。"
            if value.startswith("-") or value.startswith("/"):
                return f"技能参数“{parameter.name}”不能以命令选项开头。"
            if parameter.choices and value not in parameter.choices:
                return f"技能参数“{parameter.name}”不在管理员允许的候选值中。"
        return ""


@dataclass(frozen=True)
class SkillLoadResult:
    skills: tuple[DeclarativeCommandSkill, ...]
    issues: tuple[str, ...]


def _load_skill_file(value: Path) -> list[dict[str, Any]]:
    path = value.expanduser().resolve()
    if path.suffix.casefold() != ".json":
        raise AgentSkillError("技能文件仅支持 UTF-8 JSON 文件。")
    if not path.is_file():
        raise AgentSkillError("技能文件不存在或不是普通文件。")
    if path.stat().st_size > MAX_SKILL_FILE_BYTES:
        raise AgentSkillError(f"技能文件超过 {MAX_SKILL_FILE_BYTES // 1024} KiB。")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AgentSkillError("技能文件不是有效的 UTF-8 JSON。") from error
    if isinstance(content, dict):
        content = content.get("skills")
    if not isinstance(content, list):
        raise AgentSkillError("技能文件顶层必须是技能数组，或包含 skills 数组的对象。")
    if not all(isinstance(item, dict) for item in content):
        raise AgentSkillError("技能文件中的每一项必须是对象。")
    return content


def load_command_skill_sources(
    values: list[dict[str, Any]],
    files: list[Path],
    runner: CommandRunner,
) -> SkillLoadResult:
    """加载内联和本地 JSON 技能；坏条目被记录但不阻断机器人启动。"""
    skills: list[DeclarativeCommandSkill] = []
    names: set[str] = set()
    issues: list[str] = []
    sources: list[tuple[str, list[dict[str, Any]]]] = [("内联配置", values)]
    for file in files:
        try:
            sources.append((str(file), _load_skill_file(file)))
        except AgentSkillError as error:
            issues.append(f"技能文件 {file}：{error}")
    for source_name, entries in sources:
        for value in entries:
            try:
                skill = DeclarativeCommandSkill.from_config(value, runner)
            except AgentSkillError as error:
                issues.append(f"{source_name}：{error}")
                continue
            if skill.name in names:
                issues.append(f"{source_name}：技能“{skill.name}”名称重复，已跳过。")
                continue
            names.add(skill.name)
            skills.append(skill)
    return SkillLoadResult(tuple(skills), tuple(issues))


def load_command_skills(values: list[dict[str, Any]], runner: CommandRunner) -> tuple[DeclarativeCommandSkill, ...]:
    """兼容仅使用内联配置的旧调用。"""
    return load_command_skill_sources(values, [], runner).skills
