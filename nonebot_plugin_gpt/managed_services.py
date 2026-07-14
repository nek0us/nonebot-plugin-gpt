"""由管理员配置、可跨平台观测的受管服务状态。"""

from __future__ import annotations

import asyncio
import ctypes
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ManagedProcessService:
    name: str
    pid_file: Path
    restart_command: tuple[str, ...] = ()
    restart_check_seconds: int = 3


@dataclass(frozen=True)
class ManagedTcpService:
    name: str
    host: str
    port: int
    restart_command: tuple[str, ...] = ()
    restart_check_seconds: int = 3


class ManagedServiceRegistry:
    """只处理预先配置的服务，不暴露任意目标查询入口。"""

    def __init__(
        self,
        process_services: list[ManagedProcessService],
        tcp_services: list[ManagedTcpService],
        configuration_issues: tuple[str, ...] = (),
    ):
        self._process = {service.name: service for service in process_services}
        self._tcp = {service.name: service for service in tcp_services}
        self._configuration_issues = configuration_issues

    @classmethod
    def from_config(cls, entries: list[dict[str, Any]]) -> "ManagedServiceRegistry":
        process_services = []
        tcp_services = []
        used_names = set()
        issues = []
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                issues.append(f"第 {index} 项不是服务对象，已忽略。")
                continue
            name = str(entry.get("name", "")).strip()
            kind = str(entry.get("kind", "")).strip().lower()
            command = entry.get("restart_command", [])
            restart_command = ()
            if command not in (None, []):
                if isinstance(command, list) and all(isinstance(item, str) and item.strip() for item in command):
                    restart_command = tuple(command)
                else:
                    issues.append(f"服务第 {index} 项的重启命令格式无效，已仅注册状态查询。")
            try:
                restart_check_seconds = max(0, min(30, int(entry.get("restart_check_seconds", 3))))
            except (TypeError, ValueError):
                restart_check_seconds = 3
                issues.append(f"服务第 {index} 项的复检等待时间无效，已使用默认值 3 秒。")
            if not name or name in used_names:
                issues.append(
                    f"第 {index} 项缺少服务名称，已忽略。"
                    if not name
                    else f"服务名称“{name}”重复，后续配置已忽略。"
                )
                continue
            if kind == "pid_file":
                pid_file = entry.get("pid_file")
                if not isinstance(pid_file, str) or not pid_file.strip():
                    issues.append(f"服务“{name}”缺少有效的 PID 文件路径，已忽略。")
                    continue
                process_services.append(ManagedProcessService(name, Path(pid_file), restart_command, restart_check_seconds))
                used_names.add(name)
            elif kind == "tcp":
                host = entry.get("host")
                if not isinstance(host, str) or not host.strip():
                    issues.append(f"服务“{name}”缺少有效的主机地址，已忽略。")
                    continue
                try:
                    port = int(entry.get("port"))
                except (TypeError, ValueError):
                    issues.append(f"服务“{name}”的 TCP 端口无效，已忽略。")
                    continue
                if 1 <= port <= 65535:
                    tcp_services.append(ManagedTcpService(name, host, port, restart_command, restart_check_seconds))
                    used_names.add(name)
                else:
                    issues.append(f"服务“{name}”的 TCP 端口必须在 1 到 65535 之间，已忽略。")
            else:
                issues.append(f"服务“{name}”的类型不受支持，已忽略。")
        return cls(process_services, tcp_services, tuple(issues))

    @property
    def configuration_issues(self) -> tuple[str, ...]:
        """返回已脱敏的配置诊断，不包含命令和连接目标。"""
        return self._configuration_issues

    @property
    def process_names(self) -> tuple[str, ...]:
        return tuple(self._process)

    @property
    def tcp_names(self) -> tuple[str, ...]:
        return tuple(self._tcp)

    @property
    def restart_names(self) -> tuple[str, ...]:
        return tuple(name for name, service in {**self._process, **self._tcp}.items() if service.restart_command)

    async def overview(self) -> str:
        """汇总所有已配置服务，不暴露连接地址、PID 文件路径或重启命令。"""
        if not self._process and not self._tcp:
            return "未配置受管服务。"
        lines = ["受管服务概览"]
        for name in self.process_names:
            restart = "允许重启" if name in self.restart_names else "仅状态查询"
            lines.append(f"- {name}（PID 文件；{restart}）：{self.process_status(name).removeprefix(f'服务 {name}：')}")
        for name in self.tcp_names:
            restart = "允许重启" if name in self.restart_names else "仅状态查询"
            lines.append(f"- {name}（TCP；{restart}）：{(await self.tcp_status(name)).removeprefix(f'服务 {name}：')}")
        return "\n".join(lines)

    @staticmethod
    def _process_state(pid: int) -> str:
        """避免在 Windows 上使用 Unix 语义不稳定的 ``os.kill(pid, 0)``。"""
        if os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return "running"
                return "permission" if ctypes.get_last_error() == 5 else "missing"
            except AttributeError:
                return "unknown"
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "missing"
        except PermissionError:
            return "permission"
        except OSError:
            return "unknown"
        return "running"

    def process_status(self, name: str) -> str:
        service = self._process.get(name)
        if service is None:
            return "未找到已配置的本地服务。"
        try:
            pid = int(service.pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return f"服务 {service.name}：未运行或 PID 文件不可用。"
        state = self._process_state(pid)
        if state == "missing":
            return f"服务 {service.name}：PID {pid} 不存在。"
        if state == "permission":
            return f"服务 {service.name}：PID {pid} 存在，但当前进程无权读取详细状态。"
        if state == "unknown":
            return f"服务 {service.name}：状态暂不可用。"
        return f"服务 {service.name}：运行中（PID {pid}）。"

    async def tcp_status(self, name: str) -> str:
        service = self._tcp.get(name)
        if service is None:
            return "未找到已配置的网络服务。"

        def probe() -> bool:
            try:
                with socket.create_connection((service.host, service.port), timeout=2):
                    return True
            except OSError:
                return False

        available = await asyncio.to_thread(probe)
        state = "可连接" if available else "不可连接"
        return f"服务 {service.name}：{state}。"

    async def restart(self, name: str) -> str:
        service = self._process.get(name) or self._tcp.get(name)
        if service is None or not service.restart_command:
            return "未找到允许重启的受管服务。"
        try:
            process = await asyncio.create_subprocess_exec(
                *service.restart_command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=30)
        except (OSError, asyncio.TimeoutError):
            return f"服务 {service.name}：重启请求未成功完成。"
        if process.returncode != 0:
            return f"服务 {service.name}：重启命令返回失败状态。"
        if service.restart_check_seconds:
            await asyncio.sleep(service.restart_check_seconds)
        if isinstance(service, ManagedProcessService):
            status = self.process_status(name)
        else:
            status = await self.tcp_status(name)
        return f"服务 {service.name}：已提交重启请求；复检结果：{status.removeprefix(f'服务 {service.name}：')}"
