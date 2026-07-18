"""智能体可用的受限目录占用扫描。"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_SCAN_DEPTH = 6
MAX_SCAN_NODES = 20_000
MAX_RESULT_ENTRIES = 200


class FilesystemScanError(ValueError):
    """目录占用扫描超出管理员配置的安全边界。"""


@dataclass(frozen=True)
class ScanResult:
    root: Path
    root_name: str
    total_bytes: int
    scanned_nodes: int
    skipped_entries: int
    truncated: bool
    entries: tuple[tuple[str, int], ...]

    @staticmethod
    def _size(value: int) -> str:
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        size = float(max(0, value))
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TiB"

    def format(self) -> str:
        lines = [
            f"目录占用扫描：{self.root_name}（{self.root}）",
            f"已扫描：{self.scanned_nodes} 项；总计（受扫描边界限制）：{self._size(self.total_bytes)}",
        ]
        if self.entries:
            lines.append("占用较大的目录：")
            lines.extend(f"- {relative}: {self._size(size)}" for relative, size in self.entries)
        else:
            lines.append("未发现可统计的普通文件。")
        if self.skipped_entries:
            lines.append(f"已跳过 {self.skipped_entries} 项无权限、失效链接或无法读取的条目。")
        if self.truncated:
            lines.append(f"扫描在 {MAX_SCAN_NODES} 项或深度边界处截断；结果不是完整磁盘统计。")
        return "\n".join(lines)


class AgentFilesystemScanner:
    """只扫描管理员明确列出的目录，且永不跟随符号链接。"""

    def __init__(self, roots: list[Any]) -> None:
        configured: dict[str, Path] = {}
        for item in roots:
            if isinstance(item, dict):
                name = item.get("name", "")
                raw_path = item.get("path", "")
            else:
                name = ""
                raw_path = item
            if not isinstance(raw_path, (str, Path)):
                continue
            root = Path(raw_path).expanduser().resolve()
            if not root.is_dir():
                continue
            label = name.strip() if isinstance(name, str) else ""
            label = label or str(root)
            if label not in configured:
                configured[label] = root
        self._roots = configured

    @property
    def root_choices(self) -> tuple[str, ...]:
        return tuple(self._roots)

    @staticmethod
    def _integer(value: str, *, label: str, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except ValueError as error:
            raise FilesystemScanError(f"{label}必须是整数。") from error
        if not minimum <= parsed <= maximum:
            raise FilesystemScanError(f"{label}必须在 {minimum} 到 {maximum} 之间。")
        return parsed

    @staticmethod
    def _selected_root(arguments: dict[str, str]) -> str:
        return arguments.get("扫描目录", arguments.get("根目录", "")).strip()

    def validate(self, arguments: dict[str, str]) -> str:
        if self._selected_root(arguments) not in self._roots:
            return "扫描目录不在管理员配置的允许目录中。"
        try:
            self._integer(arguments.get("最大深度", "3"), label="最大深度", minimum=1, maximum=MAX_SCAN_DEPTH)
            self._integer(arguments.get("结果数量", "20"), label="结果数量", minimum=1, maximum=MAX_RESULT_ENTRIES)
        except FilesystemScanError as error:
            return str(error)
        return ""

    def scan(self, arguments: dict[str, str]) -> str:
        error = self.validate(arguments)
        if error:
            raise FilesystemScanError(error)
        root_name = self._selected_root(arguments)
        root = self._roots[root_name]
        max_depth = self._integer(arguments.get("最大深度", "3"), label="最大深度", minimum=1, maximum=MAX_SCAN_DEPTH)
        max_results = self._integer(arguments.get("结果数量", "20"), label="结果数量", minimum=1, maximum=MAX_RESULT_ENTRIES)
        sizes: dict[Path, int] = defaultdict(int)
        scanned_nodes = 0
        skipped_entries = 0
        truncated = False

        def visit(directory: Path, depth: int, ancestors: tuple[Path, ...]) -> None:
            nonlocal scanned_nodes, skipped_entries, truncated
            if truncated:
                return
            try:
                iterator = os.scandir(directory)
            except OSError:
                skipped_entries += 1
                return
            with iterator:
                for entry in iterator:
                    if scanned_nodes >= MAX_SCAN_NODES:
                        truncated = True
                        return
                    scanned_nodes += 1
                    try:
                        if entry.is_symlink():
                            skipped_entries += 1
                            continue
                        if entry.is_file(follow_symlinks=False):
                            size = entry.stat(follow_symlinks=False).st_size
                            for ancestor in ancestors:
                                sizes[ancestor] += size
                        elif entry.is_dir(follow_symlinks=False):
                            child = Path(entry.path)
                            if depth >= max_depth:
                                truncated = True
                                continue
                            visit(child, depth + 1, (*ancestors, child))
                    except OSError:
                        skipped_entries += 1

        visit(root, 0, (root,))
        entries = sorted(
            (
                (path.relative_to(root).as_posix() or ".", size)
                for path, size in sizes.items()
                if path != root
            ),
            key=lambda item: (-item[1], item[0]),
        )[:max_results]
        return ScanResult(
            root=root,
            root_name=root_name,
            total_bytes=sizes[root],
            scanned_nodes=scanned_nodes,
            skipped_entries=skipped_entries,
            truncated=truncated,
            entries=tuple(entries),
        ).format()
