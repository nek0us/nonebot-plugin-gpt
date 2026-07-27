"""智能体工作目录的受限文件操作。"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


MAX_FILE_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 12 * 1024 * 1024
MAX_LIST_ENTRIES = 100
MAX_SEARCH_FILES = 250
MAX_SEARCH_RESULTS = 100
MAX_SEARCH_SNIPPET = 240


class WorkspaceError(ValueError):
    """工作目录外访问或不安全的文件操作。"""


class AgentWorkspace:
    """仅允许访问一个由管理员显式指定的工作目录。"""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, value: str, *, allow_root: bool = False) -> Path:
        relative = Path(value.strip()) if value.strip() else Path(".")
        if relative.is_absolute() or ".." in relative.parts:
            raise WorkspaceError("仅允许使用工作目录内的相对路径。")
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as error:
            raise WorkspaceError("目标路径不在智能体工作目录内。") from error
        if not allow_root and target == self.root:
            raise WorkspaceError("请提供工作目录内的文件路径。")
        return target

    def resolve_relative(self, value: str, *, allow_root: bool = False) -> Path:
        """返回经边界校验的工作区路径，供受限执行器复用。"""
        return self._path(value, allow_root=allow_root)

    def list_files(self, value: str = "") -> str:
        target = self._path(value, allow_root=True)
        if not target.exists():
            raise WorkspaceError("指定目录不存在。")
        if not target.is_dir():
            raise WorkspaceError("指定路径不是目录。")
        entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        lines = ["工作目录文件列表："]
        for item in entries[:MAX_LIST_ENTRIES]:
            relative = item.relative_to(self.root).as_posix()
            lines.append(f"- {relative}{'/' if item.is_dir() else ''}")
        if len(entries) > MAX_LIST_ENTRIES:
            lines.append(f"- 其余 {len(entries) - MAX_LIST_ENTRIES} 项未显示")
        return "\n".join(lines) if len(lines) > 1 else "工作目录为空。"

    def describe_path(self, value: str = "") -> str:
        """返回工作区内单一路径的安全元数据，不读取文件正文。"""
        target = self._path(value, allow_root=True)
        if not target.exists():
            raise WorkspaceError("指定路径不存在。")
        relative = "." if target == self.root else target.relative_to(self.root).as_posix()
        if target.is_dir():
            count = sum(1 for _ in target.iterdir())
            return f"目录：{relative}\n直接子项：{count}"
        if not target.is_file():
            raise WorkspaceError("指定路径不是普通文件或目录。")
        stat = target.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return "\n".join((
            f"文件：{relative}",
            f"大小：{stat.st_size} 字节",
            f"修改时间：{modified}",
        ))

    def read_text(self, value: str) -> str:
        target = self._path(value)
        if not target.exists() or not target.is_file():
            raise WorkspaceError("指定文件不存在或不是普通文件。")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise WorkspaceError(f"文件超过 {MAX_FILE_BYTES // 1024} KiB，拒绝读取。")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise WorkspaceError("仅支持读取 UTF-8 文本文件。") from error
        return f"文件：{target.relative_to(self.root).as_posix()}\n\n{content}"

    def write_text(self, value: str, content: str) -> str:
        target = self._path(value)
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise WorkspaceError(f"写入内容超过 {MAX_FILE_BYTES // 1024} KiB，已拒绝。")
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("wb", delete=False, dir=target.parent, prefix=".agent-") as temporary:
            temporary.write(encoded)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, target)
        finally:
            temporary_path.unlink(missing_ok=True)
        return f"已写入工作目录文件：{target.relative_to(self.root).as_posix()}（{len(encoded)} 字节）"

    def make_directory(self, value: str) -> str:
        target = self._path(value)
        if target.exists():
            if target.is_dir():
                return f"工作目录已存在：{target.relative_to(self.root).as_posix()}/"
            raise WorkspaceError("同名文件已存在，不能创建目录。")
        target.mkdir(parents=True, exist_ok=False)
        return f"已创建工作目录：{target.relative_to(self.root).as_posix()}/"

    def append_text(self, value: str, content: str) -> str:
        target = self._path(value)
        if target.exists():
            if not target.is_file():
                raise WorkspaceError("指定路径不是普通文件，不能追加文本。")
            if target.stat().st_size > MAX_FILE_BYTES:
                raise WorkspaceError(f"文件超过 {MAX_FILE_BYTES // 1024} KiB，拒绝追加。")
            try:
                previous = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                raise WorkspaceError("仅支持向 UTF-8 文本文件追加内容。") from error
        else:
            previous = ""
        combined = previous + content
        encoded = combined.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise WorkspaceError(f"追加后内容超过 {MAX_FILE_BYTES // 1024} KiB，已拒绝。")
        self.write_text(value, combined)
        return f"已追加工作目录文件：{target.relative_to(self.root).as_posix()}（新增 {len(content.encode('utf-8'))} 字节）"

    def replace_text(self, value: str, search: str, replacement: str, *, maximum: int = 0) -> str:
        if not search:
            raise WorkspaceError("待替换文本不能为空。")
        if maximum < 0:
            raise WorkspaceError("最大替换次数不能小于 0。")
        target = self._path(value)
        if not target.exists() or not target.is_file():
            raise WorkspaceError("指定文件不存在或不是普通文件。")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise WorkspaceError(f"文件超过 {MAX_FILE_BYTES // 1024} KiB，拒绝替换。")
        try:
            previous = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise WorkspaceError("仅支持替换 UTF-8 文本文件。") from error
        occurrences = previous.count(search)
        if not occurrences:
            raise WorkspaceError("文件中未找到待替换文本，未修改文件。")
        count = min(occurrences, maximum) if maximum else occurrences
        updated = previous.replace(search, replacement, count)
        if len(updated.encode("utf-8")) > MAX_FILE_BYTES:
            raise WorkspaceError(f"替换后内容超过 {MAX_FILE_BYTES // 1024} KiB，已拒绝。")
        self.write_text(value, updated)
        return f"已替换工作目录文件：{target.relative_to(self.root).as_posix()}（{count} 处）"

    def search_text(
        self,
        query: str,
        value: str = "",
        *,
        ignore_case: bool = False,
        maximum_results: int = 30,
    ) -> str:
        """在受限目录内搜索小型 UTF-8 文本文件，按行返回有限摘要。"""
        if not query.strip():
            raise WorkspaceError("搜索文本不能为空。")
        if not 1 <= maximum_results <= MAX_SEARCH_RESULTS:
            raise WorkspaceError(f"结果数量必须在 1 到 {MAX_SEARCH_RESULTS} 之间。")
        root = self._path(value, allow_root=True)
        if not root.exists() or not root.is_dir():
            raise WorkspaceError("搜索路径不存在或不是目录。")
        needle = query.casefold() if ignore_case else query
        lines = [f"工作目录搜索：{query}"]
        scanned = 0
        matches = 0
        for directory, subdirectories, files in os.walk(root, followlinks=False):
            subdirectories[:] = [name for name in subdirectories if not (Path(directory) / name).is_symlink()]
            for name in sorted(files):
                if scanned >= MAX_SEARCH_FILES or matches >= maximum_results:
                    break
                target = Path(directory) / name
                if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_FILE_BYTES:
                    continue
                scanned += 1
                try:
                    content = target.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for line_number, line in enumerate(content.splitlines(), start=1):
                    comparable = line.casefold() if ignore_case else line
                    if needle not in comparable:
                        continue
                    relative = target.relative_to(self.root).as_posix()
                    snippet = line.strip()
                    if len(snippet) > MAX_SEARCH_SNIPPET:
                        snippet = f"{snippet[:MAX_SEARCH_SNIPPET - 1]}…"
                    lines.append(f"- {relative}:{line_number}: {snippet}")
                    matches += 1
                    if matches >= maximum_results:
                        break
            if scanned >= MAX_SEARCH_FILES or matches >= maximum_results:
                break
        if matches == 0:
            lines.append("未找到匹配文本。")
        if scanned >= MAX_SEARCH_FILES:
            lines.append(f"仅扫描前 {MAX_SEARCH_FILES} 个可读文本文件。")
        if matches >= maximum_results:
            lines.append(f"结果已限制为前 {maximum_results} 项。")
        return "\n".join(lines)

    def copy_file(self, source: str, destination: str) -> str:
        source_path = self._path(source)
        destination_path = self._path(destination)
        if not source_path.exists() or not source_path.is_file():
            raise WorkspaceError("来源文件不存在或不是普通文件。")
        if destination_path.exists():
            raise WorkspaceError("目标路径已存在；为避免覆盖，已拒绝复制。")
        if source_path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise WorkspaceError(f"来源文件超过 {MAX_ARTIFACT_BYTES // (1024 * 1024)} MiB，拒绝复制。")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        return f"已复制工作目录文件：{source_path.relative_to(self.root).as_posix()} -> {destination_path.relative_to(self.root).as_posix()}"

    def move_file(self, source: str, destination: str) -> str:
        source_path = self._path(source)
        destination_path = self._path(destination)
        if not source_path.exists() or not source_path.is_file():
            raise WorkspaceError("来源文件不存在或不是普通文件。")
        if destination_path.exists():
            raise WorkspaceError("目标路径已存在；为避免覆盖，已拒绝移动。")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_path, destination_path)
        return f"已移动工作目录文件：{source_path.relative_to(self.root).as_posix()} -> {destination_path.relative_to(self.root).as_posix()}"

    def delete_file(self, value: str) -> str:
        target = self._path(value)
        if not target.exists() or not target.is_file():
            raise WorkspaceError("只能删除工作目录内存在的普通文件。")
        relative = target.relative_to(self.root).as_posix()
        target.unlink()
        return f"已删除工作目录文件：{relative}"

    def write_bytes(self, value: str, content: bytes) -> str:
        target = self._path(value)
        if len(content) > MAX_ARTIFACT_BYTES:
            raise WorkspaceError(f"二进制产物超过 {MAX_ARTIFACT_BYTES // (1024 * 1024)} MiB，已拒绝写入。")
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("wb", delete=False, dir=target.parent, prefix=".agent-") as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, target)
        finally:
            temporary_path.unlink(missing_ok=True)
        return f"已写入工作目录产物：{target.relative_to(self.root).as_posix()}（{len(content)} 字节）"

    def read_bytes(self, value: str, *, maximum_bytes: int = MAX_ARTIFACT_BYTES) -> bytes:
        target = self._path(value)
        if not target.exists() or not target.is_file():
            raise WorkspaceError("指定产物不存在或不是普通文件。")
        if target.stat().st_size > maximum_bytes:
            raise WorkspaceError(f"产物超过 {maximum_bytes // (1024 * 1024)} MiB，拒绝读取。")
        return target.read_bytes()
