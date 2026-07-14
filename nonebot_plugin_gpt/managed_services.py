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


@dataclass(frozen=True)
class ManagedTcpService:
    name: str
    host: str
    port: int


class ManagedServiceRegistry:
    """只处理预先配置的服务，不暴露任意目标查询入口。"""

    def __init__(self, process_services: list[ManagedProcessService], tcp_services: list[ManagedTcpService]):
        self._process = {service.name: service for service in process_services}
        self._tcp = {service.name: service for service in tcp_services}

    @classmethod
    def from_config(cls, entries: list[dict[str, Any]]) -> "ManagedServiceRegistry":
        process_services = []
        tcp_services = []
        used_names = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            kind = str(entry.get("kind", "")).strip().lower()
            if not name or name in used_names:
                continue
            if kind == "pid_file" and isinstance(entry.get("pid_file"), str):
                process_services.append(ManagedProcessService(name, Path(entry["pid_file"])))
                used_names.add(name)
            elif kind == "tcp" and isinstance(entry.get("host"), str):
                try:
                    port = int(entry.get("port"))
                except (TypeError, ValueError):
                    continue
                if 1 <= port <= 65535:
                    tcp_services.append(ManagedTcpService(name, entry["host"], port))
                    used_names.add(name)
        return cls(process_services, tcp_services)

    @property
    def process_names(self) -> tuple[str, ...]:
        return tuple(self._process)

    @property
    def tcp_names(self) -> tuple[str, ...]:
        return tuple(self._tcp)

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
