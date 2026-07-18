"""智能体工作目录的受限文件操作。"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


MAX_FILE_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 12 * 1024 * 1024
MAX_LIST_ENTRIES = 100


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
