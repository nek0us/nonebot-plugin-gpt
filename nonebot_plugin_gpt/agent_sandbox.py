"""工作区脚本的显式隔离执行后端。"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .agent_workspace import AgentWorkspace, WorkspaceError


SandboxBackend = Literal["disabled", "local", "docker"]


class SandboxError(ValueError):
    """受限脚本执行配置或请求不符合边界。"""


@dataclass(frozen=True)
class SandboxResult:
    return_code: int
    output: str

    def format(self) -> str:
        return "\n".join((
            f"脚本退出码：{self.return_code}",
            "输出：",
            self.output or "（无输出）",
        ))


class WorkspaceSandbox:
    """只运行工作区中的 Python 脚本；Docker 模式默认无网络。"""

    def __init__(
        self,
        workspace: AgentWorkspace,
        *,
        backend: SandboxBackend = "disabled",
        image: str = "",
        timeout_seconds: int = 60,
        memory_mb: int = 512,
    ) -> None:
        if backend not in {"disabled", "local", "docker"}:
            raise SandboxError("执行后端必须是 disabled、local 或 docker。")
        if not 1 <= timeout_seconds <= 600:
            raise SandboxError("脚本超时必须在 1 到 600 秒之间。")
        if not 64 <= memory_mb <= 4096:
            raise SandboxError("脚本内存上限必须在 64 到 4096 MiB 之间。")
        if backend == "docker" and not image.strip():
            raise SandboxError("Docker 执行后端需要配置镜像。")
        self.workspace = workspace
        self.backend = backend
        self.image = image.strip()
        self.timeout_seconds = timeout_seconds
        self.memory_mb = memory_mb

    @property
    def enabled(self) -> bool:
        return self.backend != "disabled"

    def validate(self, script: str, raw_arguments: str = "[]") -> tuple[Path, tuple[str, ...]]:
        if self.backend == "disabled":
            raise SandboxError("工作区脚本执行尚未启用。")
        try:
            target = self.workspace.resolve_relative(script)
        except WorkspaceError as error:
            raise SandboxError(str(error)) from error
        if target.suffix.casefold() != ".py":
            raise SandboxError("当前仅允许执行工作区内的 .py 脚本。")
        if not target.is_file():
            raise SandboxError("脚本不存在或不是普通文件。")
        try:
            values = json.loads(raw_arguments or "[]")
        except json.JSONDecodeError as error:
            raise SandboxError("脚本参数必须是 JSON 字符串数组。") from error
        if not isinstance(values, list) or len(values) > 32 or not all(isinstance(item, str) for item in values):
            raise SandboxError("脚本参数必须是最多 32 项的 JSON 字符串数组。")
        if any("\x00" in item or len(item) > 2048 for item in values):
            raise SandboxError("脚本参数包含非法或过长内容。")
        return target, tuple(values)

    async def run(self, script: str, raw_arguments: str = "[]") -> str:
        target, arguments = self.validate(script, raw_arguments)
        relative_script = target.relative_to(self.workspace.root).as_posix()
        if self.backend == "local":
            command = (sys.executable, str(target), *arguments)
            cwd = str(self.workspace.root)
        else:
            if shutil.which("docker") is None:
                raise SandboxError("未找到 docker 命令，无法启动隔离执行后端。")
            command = (
                "docker", "run", "--pull", "never", "--rm", "--network", "none", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "64",
                "--memory", f"{self.memory_mb}m", "--cpus", "1",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                "--workdir", "/workspace", "-v", f"{self.workspace.root}:/workspace:rw",
                self.image, "python", f"/workspace/{relative_script}", *arguments,
            )
            cwd = None
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return f"脚本超时，已终止（{self.timeout_seconds} 秒）。"
        return SandboxResult(
            process.returncode or 0,
            output.decode("utf-8", errors="replace")[:12000].strip(),
        ).format()
