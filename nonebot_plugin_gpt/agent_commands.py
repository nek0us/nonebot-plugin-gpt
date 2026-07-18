"""跨平台、无 Shell 的受控命令执行能力。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CommandValidationError(ValueError):
    """命令提案不满足本地安全边界。"""


@dataclass(frozen=True)
class CommandSpec:
    program: str
    arguments: tuple[str, ...]
    working_directory: Path | None
    timeout_seconds: int

    @classmethod
    def from_agent_arguments(
        cls,
        arguments: dict[str, str],
        *,
        default_timeout_seconds: int,
        allowed_root: Path | None,
    ) -> "CommandSpec":
        program = arguments.get("程序", "").strip()
        if not program or "\x00" in program or len(program) > 512:
            raise CommandValidationError("程序必须是长度不超过 512 的非空字符串。")
        raw_arguments = arguments.get("参数", "[]")
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as error:
            raise CommandValidationError("参数必须是 JSON 字符串数组。") from error
        if not isinstance(parsed, list) or len(parsed) > 64 or not all(isinstance(item, str) for item in parsed):
            raise CommandValidationError("参数必须是最多 64 项的 JSON 字符串数组。")
        if any("\x00" in item or len(item) > 4096 for item in parsed):
            raise CommandValidationError("命令参数包含非法或过长内容。")
        timeout = default_timeout_seconds
        if arguments.get("超时秒数", "").strip():
            try:
                timeout = int(arguments["超时秒数"])
            except ValueError as error:
                raise CommandValidationError("超时秒数必须是整数。") from error
        if not 1 <= timeout <= 600:
            raise CommandValidationError("超时秒数必须在 1 到 600 之间。")

        working_directory: Path | None = None
        raw_directory = arguments.get("工作目录", "").strip()
        if raw_directory:
            candidate = Path(raw_directory).expanduser().resolve()
            if allowed_root is not None:
                try:
                    candidate.relative_to(allowed_root)
                except ValueError as error:
                    raise CommandValidationError("工作目录必须位于配置的命令工作目录内。") from error
            if not candidate.is_dir():
                raise CommandValidationError("工作目录不存在或不是目录。")
            working_directory = candidate
        elif allowed_root is not None:
            working_directory = allowed_root
        return cls(program, tuple(parsed), working_directory, timeout)

    def display(self) -> str:
        values = [self.program, *self.arguments]
        rendered = " ".join(json.dumps(item, ensure_ascii=False) for item in values)
        directory = str(self.working_directory) if self.working_directory else "继承机器人进程目录"
        return f"命令：{rendered}\n工作目录：{directory}\n超时：{self.timeout_seconds} 秒"


class CommandRunner:
    """只运行明确 argv，不解释 shell 元字符。"""

    def __init__(self, *, default_timeout_seconds: int = 30, working_directory: Path | None = None) -> None:
        self._default_timeout_seconds = max(1, min(default_timeout_seconds, 600))
        self._working_directory = working_directory.expanduser().resolve() if working_directory else None
        if self._working_directory is not None:
            self._working_directory.mkdir(parents=True, exist_ok=True)

    def parse(self, arguments: dict[str, str]) -> CommandSpec:
        return CommandSpec.from_agent_arguments(
            arguments,
            default_timeout_seconds=self._default_timeout_seconds,
            allowed_root=self._working_directory,
        )

    async def run(self, arguments: dict[str, str]) -> str:
        spec = self.parse(arguments)
        process = await asyncio.create_subprocess_exec(
            spec.program,
            *spec.arguments,
            cwd=str(spec.working_directory) if spec.working_directory else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=spec.timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return f"命令超时，已终止。\n{spec.display()}"
        text = output.decode("utf-8", errors="replace")[:12000].strip()
        return "\n".join([
            f"命令退出码：{process.returncode}",
            spec.display(),
            "输出：",
            text or "（无输出）",
        ])
