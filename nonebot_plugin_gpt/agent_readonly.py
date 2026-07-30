"""管理员命名的只读诊断根目录。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_LIST_ENTRIES = 120
MAX_EXCERPT_LINES = 400
MAX_TAIL_LINES = 400
MAX_LINE_CHARS = 1_200
MAX_SEARCH_FILES = 400
MAX_SEARCH_RESULTS = 100
MAX_SEARCH_FILE_BYTES = 8 * 1024 * 1024
MAX_SEARCH_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SEARCH_SNIPPET = 300
MAX_TAIL_BYTES = 512 * 1024
MAX_ANALYZE_BYTES = 512 * 1024 * 1024
MAX_ANALYZE_MATCHES = 30


class ReadonlySourceError(ValueError):
    """只读诊断目录边界或输入不合法。"""


@dataclass(frozen=True)
class ReadonlyRoot:
    name: str
    path: Path


@dataclass(frozen=True)
class ReadonlyRoute:
    root_name: str
    relative_path: str


class AgentReadonlyRoots:
    """只允许在管理员配置的命名目录内读取、搜索，不跟随符号链接。"""

    def __init__(self, roots: list[Any]) -> None:
        configured: dict[str, ReadonlyRoot] = {}
        for item in roots:
            if isinstance(item, dict):
                raw_name = item.get("name", "")
                raw_path = item.get("path", "")
            else:
                raw_name = ""
                raw_path = item
            if not isinstance(raw_path, (str, Path)):
                continue
            path = Path(raw_path).expanduser().resolve()
            if not path.is_dir():
                continue
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                continue
            if name not in configured:
                configured[name] = ReadonlyRoot(name, path)
        self._roots = configured

    @property
    def root_choices(self) -> tuple[str, ...]:
        return tuple(self._roots)

    def routing_guide(self) -> str:
        """Return host-provided path mappings for agent decision prompts.

        Agent tools accept a named root and a relative path, whereas people
        naturally refer to project-relative or absolute paths. This guide keeps
        the model from treating a source path as a path in the separate
        writable workspace. Local validation remains the security boundary.
        """
        if not self._roots:
            return ""
        lines = [
            "【主机路径路由】以下是已注册只读工具的真实路径映射，不是用户猜测。",
            "对这些路径，必须选择对应的“根目录”枚举值，并只填写根目录后的相对部分；"
            "不要把它们交给工作区工具，也不要在最终回答中猜测未读取到的源码内容。",
        ]
        for root in self._roots.values():
            host_path = root.path.as_posix()
            segment = root.path.name
            example = f"{segment}/..." if segment else "<根目录>/..."
            lines.append(
                f"- “{root.name}” = `{host_path}`。用户提到 `{host_path}/...` 或"
                f"项目相对路径 `{example}` 时，选择“{root.name}”，"
                f"并去掉 `{host_path}/` 或 `{segment}/` 前缀。"
            )
        return "\n".join(lines)

    def route_path(self, value: str) -> ReadonlyRoute | None:
        """Map an absolute or project-relative user path to a named root."""
        candidate = value.strip().strip("`'\"，。；：！？（）()[]{}")
        if not candidate:
            return None
        normalized = candidate.replace("\\", "/").rstrip("/")
        for root in self._roots.values():
            host_path = root.path.as_posix().rstrip("/")
            if normalized == host_path:
                return ReadonlyRoute(root.name, "")
            if normalized.startswith(f"{host_path}/"):
                return ReadonlyRoute(root.name, normalized[len(host_path) + 1:])
            segment = root.path.name
            if segment and normalized == segment:
                return ReadonlyRoute(root.name, "")
            if segment and normalized.startswith(f"{segment}/"):
                return ReadonlyRoute(root.name, normalized[len(segment) + 1:])
        return None

    def route_task_path(self, task: str) -> ReadonlyRoute | None:
        """Find the most specific configured path reference in a task."""
        matches: list[tuple[int, ReadonlyRoute]] = []
        for candidate in re.findall(r"(?:[A-Za-z]:)?[A-Za-z0-9_./\\-]+", task):
            if route := self.route_path(candidate):
                matches.append((len(candidate), route))
        return max(matches, default=(0, None), key=lambda item: item[0])[1]

    @staticmethod
    def _integer(value: str, *, label: str, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise ReadonlySourceError(f"{label}必须是整数。") from error
        if not minimum <= parsed <= maximum:
            raise ReadonlySourceError(f"{label}必须在 {minimum} 到 {maximum} 之间。")
        return parsed

    def _root(self, name: str) -> ReadonlyRoot:
        root = self._roots.get(name.strip())
        if root is None:
            raise ReadonlySourceError("只读根目录不在管理员允许的目录中。")
        return root

    def _path(self, root: ReadonlyRoot, value: str = "", *, allow_root: bool = False) -> Path:
        relative = Path(value.strip()) if value.strip() else Path(".")
        if relative.is_absolute() or ".." in relative.parts:
            raise ReadonlySourceError("只能使用所选根目录内的相对路径。")
        target = root.path / relative
        try:
            resolved = target.resolve(strict=False)
            resolved.relative_to(root.path)
        except ValueError as error:
            raise ReadonlySourceError("目标路径不在所选只读根目录内。") from error
        if not allow_root and resolved == root.path:
            raise ReadonlySourceError("请提供根目录内的文件路径。")
        if target.is_symlink() or (target.exists() and resolved.is_symlink()):
            raise ReadonlySourceError("不允许读取符号链接。")
        return resolved

    @staticmethod
    def _relative(root: ReadonlyRoot, target: Path) -> str:
        return "." if target == root.path else target.relative_to(root.path).as_posix()

    @staticmethod
    def _snippet(value: str) -> str:
        text = value.strip().replace("\t", "    ")
        return text if len(text) <= MAX_SEARCH_SNIPPET else f"{text[:MAX_SEARCH_SNIPPET - 1]}…"

    @staticmethod
    def _line(value: str) -> str:
        return value.rstrip("\r\n") if len(value) <= MAX_LINE_CHARS else f"{value[:MAX_LINE_CHARS - 1]}…"

    @staticmethod
    def _size(value: int) -> str:
        units = ("B", "KiB", "MiB", "GiB", "TiB")
        size = float(max(0, value))
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TiB"

    def validate_list(self, arguments: dict[str, str]) -> str:
        try:
            self._path(self._root(arguments.get("根目录", "")), arguments.get("路径", ""), allow_root=True)
        except ReadonlySourceError as error:
            return str(error)
        return ""

    def validate_excerpt(self, arguments: dict[str, str]) -> str:
        try:
            root = self._root(arguments.get("根目录", ""))
            target = self._path(root, arguments.get("文件", ""))
            if not target.is_file():
                raise ReadonlySourceError("指定路径不是普通文件。")
            self._integer(arguments.get("起始行", "1"), label="起始行", minimum=1, maximum=10_000_000)
            self._integer(arguments.get("行数", "120"), label="行数", minimum=1, maximum=MAX_EXCERPT_LINES)
        except ReadonlySourceError as error:
            return str(error)
        return ""

    def validate_tail(self, arguments: dict[str, str]) -> str:
        try:
            root = self._root(arguments.get("根目录", ""))
            target = self._path(root, arguments.get("文件", ""))
            if not target.is_file():
                raise ReadonlySourceError("指定路径不是普通文件。")
            self._integer(arguments.get("行数", "120"), label="行数", minimum=1, maximum=MAX_TAIL_LINES)
        except ReadonlySourceError as error:
            return str(error)
        return ""

    def validate_search(self, arguments: dict[str, str]) -> str:
        try:
            if not arguments.get("文本", "").strip():
                raise ReadonlySourceError("搜索文本不能为空。")
            if len(arguments["文本"]) > 512:
                raise ReadonlySourceError("搜索文本不能超过 512 个字符。")
            root = self._root(arguments.get("根目录", ""))
            self._path(root, arguments.get("路径", ""), allow_root=True)
            self._integer(arguments.get("结果数量", "30"), label="结果数量", minimum=1, maximum=MAX_SEARCH_RESULTS)
        except ReadonlySourceError as error:
            return str(error)
        return ""

    def validate_analyze(self, arguments: dict[str, str]) -> str:
        try:
            root = self._root(arguments.get("根目录", ""))
            target = self._path(root, arguments.get("文件", ""))
            if not target.is_file():
                raise ReadonlySourceError("指定路径不是普通文件。")
            query = arguments.get("关键词", "").strip()
            if len(query) > 512:
                raise ReadonlySourceError("关键词不能超过 512 个字符。")
        except ReadonlySourceError as error:
            return str(error)
        return ""

    def list_entries(self, arguments: dict[str, str]) -> str:
        error = self.validate_list(arguments)
        if error:
            raise ReadonlySourceError(error)
        root = self._root(arguments["根目录"])
        target = self._path(root, arguments.get("路径", ""), allow_root=True)
        if not target.exists() or not target.is_dir():
            raise ReadonlySourceError("指定路径不存在或不是目录。")
        entries = []
        skipped = 0
        for item in sorted(target.iterdir(), key=lambda path: (not path.is_dir(), path.name.casefold())):
            if item.is_symlink():
                skipped += 1
                continue
            entries.append(item)
        relative = self._relative(root, target)
        lines = [f"只读目录：{root.name}/{relative}"]
        for item in entries[:MAX_LIST_ENTRIES]:
            child = self._relative(root, item)
            lines.append(f"- {child}{'/' if item.is_dir() else ''}")
        if len(entries) > MAX_LIST_ENTRIES:
            lines.append(f"- 其余 {len(entries) - MAX_LIST_ENTRIES} 项未显示")
        if skipped:
            lines.append(f"- 已跳过 {skipped} 个符号链接")
        return "\n".join(lines) if len(lines) > 1 else "目录为空。"

    def describe_path(self, arguments: dict[str, str]) -> str:
        error = self.validate_list(arguments)
        if error:
            raise ReadonlySourceError(error)
        root = self._root(arguments["根目录"])
        target = self._path(root, arguments.get("路径", ""), allow_root=True)
        if not target.exists():
            raise ReadonlySourceError("指定路径不存在。")
        relative = self._relative(root, target)
        if target.is_dir():
            count = sum(1 for item in target.iterdir() if not item.is_symlink())
            return f"只读目录：{root.name}/{relative}\n直接子项：{count}"
        if not target.is_file():
            raise ReadonlySourceError("指定路径不是普通文件或目录。")
        stat = target.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return "\n".join((
            f"只读文件：{root.name}/{relative}",
            f"大小：{stat.st_size} 字节",
            f"修改时间：{modified}",
        ))

    def read_excerpt(self, arguments: dict[str, str]) -> str:
        error = self.validate_excerpt(arguments)
        if error:
            raise ReadonlySourceError(error)
        root = self._root(arguments["根目录"])
        target = self._path(root, arguments["文件"])
        start_line = self._integer(arguments.get("起始行", "1"), label="起始行", minimum=1, maximum=10_000_000)
        line_count = self._integer(arguments.get("行数", "120"), label="行数", minimum=1, maximum=MAX_EXCERPT_LINES)
        collected: list[str] = []
        try:
            with target.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if line_number < start_line:
                        continue
                    if len(collected) >= line_count:
                        break
                    collected.append(f"{line_number}: {self._line(line)}")
        except (OSError, UnicodeDecodeError) as error:
            raise ReadonlySourceError("只能读取可访问的 UTF-8 文本文件。") from error
        relative = self._relative(root, target)
        if not collected:
            return f"只读文件：{root.name}/{relative}\n起始行之后没有内容。"
        return f"只读文件：{root.name}/{relative}\n行 {start_line} 起：\n" + "\n".join(collected)

    def read_tail(self, arguments: dict[str, str]) -> str:
        error = self.validate_tail(arguments)
        if error:
            raise ReadonlySourceError(error)
        root = self._root(arguments["根目录"])
        target = self._path(root, arguments["文件"])
        line_count = self._integer(arguments.get("行数", "120"), label="行数", minimum=1, maximum=MAX_TAIL_LINES)
        try:
            with target.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - MAX_TAIL_BYTES))
                content = handle.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ReadonlySourceError("只能读取可访问的 UTF-8 文本文件。") from error
        lines = content.splitlines()[-line_count:]
        relative = self._relative(root, target)
        prefix = "文件末尾片段" if size <= MAX_TAIL_BYTES else f"文件末尾 {MAX_TAIL_BYTES // 1024} KiB 片段"
        return f"{prefix}：{root.name}/{relative}\n" + "\n".join(self._line(line) for line in lines)

    def analyze_text(self, arguments: dict[str, str]) -> str:
        """对一个受限 UTF-8 文本做通用结构统计和可选关键词分析。"""
        error = self.validate_analyze(arguments)
        if error:
            raise ReadonlySourceError(error)
        root = self._root(arguments["根目录"])
        target = self._path(root, arguments["文件"])
        try:
            stat = target.stat()
        except OSError as error:
            raise ReadonlySourceError("无法读取目标文件元数据。") from error
        if stat.st_size > MAX_ANALYZE_BYTES:
            raise ReadonlySourceError(
                f"文件超过 {MAX_ANALYZE_BYTES // (1024 * 1024)} MiB 分析上限；请先用读取文件尾部或缩小文件范围。"
            )
        query = arguments.get("关键词", "").strip()
        line_count = 0
        matched_lines = 0
        matches: list[str] = []
        try:
            with target.open("r", encoding="utf-8") as handle:
                for line_count, line in enumerate(handle, start=1):
                    if query and query in line:
                        matched_lines += 1
                        if len(matches) < MAX_ANALYZE_MATCHES:
                            matches.append(f"- {line_count}: {self._snippet(line)}")
        except (OSError, UnicodeDecodeError) as error:
            raise ReadonlySourceError("只能分析可访问的 UTF-8 文本文件。") from error
        relative = self._relative(root, target)
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"文本分析：{root.name}/{relative}",
            f"大小：{self._size(stat.st_size)}",
            f"总行数：{line_count}",
            f"修改时间：{modified}",
        ]
        if query:
            lines.append(f"关键词“{query}”命中行数：{matched_lines}")
            lines.extend(matches)
            if matched_lines > len(matches):
                lines.append(f"其余 {matched_lines - len(matches)} 个命中行未显示；可用读取文件片段查看指定行。")
        return "\n".join(lines)

    def search_text(self, arguments: dict[str, str]) -> str:
        error = self.validate_search(arguments)
        if error:
            raise ReadonlySourceError(error)
        root = self._root(arguments["根目录"])
        start = self._path(root, arguments.get("路径", ""), allow_root=True)
        if not start.exists() or not start.is_dir():
            raise ReadonlySourceError("搜索路径不存在或不是目录。")
        query = arguments["文本"]
        ignore_case = arguments.get("忽略大小写", "否") == "是"
        needle = query.casefold() if ignore_case else query
        maximum = self._integer(arguments.get("结果数量", "30"), label="结果数量", minimum=1, maximum=MAX_SEARCH_RESULTS)
        lines = [f"只读搜索：{root.name}，文本：{query}"]
        scanned_files = 0
        scanned_bytes = 0
        matches = 0
        truncated = False
        for directory, directories, files in os.walk(start, followlinks=False):
            directories[:] = sorted(name for name in directories if not (Path(directory) / name).is_symlink())
            for name in sorted(files):
                target = Path(directory) / name
                try:
                    if target.is_symlink() or not target.is_file():
                        continue
                    size = target.stat().st_size
                except OSError:
                    continue
                if size > MAX_SEARCH_FILE_BYTES:
                    continue
                if scanned_files >= MAX_SEARCH_FILES or scanned_bytes + size > MAX_SEARCH_TOTAL_BYTES:
                    truncated = True
                    break
                scanned_files += 1
                scanned_bytes += size
                try:
                    with target.open("r", encoding="utf-8") as handle:
                        for line_number, line in enumerate(handle, start=1):
                            comparable = line.casefold() if ignore_case else line
                            if needle not in comparable:
                                continue
                            lines.append(f"- {self._relative(root, target)}:{line_number}: {self._snippet(line)}")
                            matches += 1
                            if matches >= maximum:
                                break
                except (OSError, UnicodeDecodeError):
                    continue
                if matches >= maximum:
                    break
            if truncated or matches >= maximum:
                break
        if matches == 0:
            lines.append("未找到匹配文本。")
        if truncated:
            lines.append("搜索达到文件数量或总读取量限制；可缩小路径或改用读取文件尾部。")
        if matches >= maximum:
            lines.append(f"结果已限制为前 {maximum} 项。")
        return "\n".join(lines)
