"""不执行外部命令的跨平台本机环境诊断。"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


def _format_bytes(value: int | None) -> str:
    if value is None or value < 0:
        return "不可用"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return "不可用"


def _windows_memory_total() -> int | None:
    """通过 Windows API 读取物理内存，不引入额外的系统信息依赖。"""

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    try:
        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
    except (AttributeError, OSError):
        pass
    return None


def _memory_total(system: str) -> int | None:
    if system == "Windows":
        return _windows_memory_total()
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return None


def collect_environment_diagnostics() -> dict[str, Any]:
    """收集可安全发送给超级用户的本机基础诊断信息。"""
    system = platform.system() or os.name
    disk_target = Path.cwd().anchor or os.path.sep
    try:
        disk = shutil.disk_usage(disk_target)
        disk_total, disk_free = disk.total, disk.free
    except OSError:
        disk_total = disk_free = None

    load_average: tuple[float, float, float] | None = None
    getloadavg = getattr(os, "getloadavg", None)
    if callable(getloadavg):
        try:
            load_average = tuple(round(value, 2) for value in getloadavg())
        except OSError:
            pass

    return {
        "system": system,
        "release": platform.release() or "未知",
        "machine": platform.machine() or "未知",
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "memory_total": _memory_total(system),
        "disk_target": disk_target,
        "disk_total": disk_total,
        "disk_free": disk_free,
        "load_average": load_average,
    }


def format_environment_diagnostics(diagnostics: dict[str, Any]) -> str:
    """将诊断结构投影为适合跨平台消息发送的短文本。"""
    load_average = diagnostics.get("load_average")
    load_text = " / ".join(str(value) for value in load_average) if load_average else "不适用"
    cpu_count = diagnostics.get("cpu_count")
    cpu_text = f"{cpu_count} 核" if isinstance(cpu_count, int) and cpu_count > 0 else "不可用"
    return "\n".join([
        "本机环境诊断",
        (
            f"系统：{diagnostics.get('system', '未知')} "
            f"{diagnostics.get('release', '未知')}（{diagnostics.get('machine', '未知')}）"
        ),
        f"Python：{diagnostics.get('python', '未知')}｜CPU：{cpu_text}",
        f"内存总量：{_format_bytes(diagnostics.get('memory_total'))}",
        (
            f"磁盘 {diagnostics.get('disk_target', os.path.sep)}："
            f"可用 {_format_bytes(diagnostics.get('disk_free'))} / 总计 {_format_bytes(diagnostics.get('disk_total'))}"
        ),
        f"系统负载（1/5/15 分钟）：{load_text}",
    ])
