"""将工作区内静态 HTML 渲染为可回传截图。"""

from __future__ import annotations

import re
from pathlib import Path

from .agent_workspace import AgentWorkspace, WorkspaceError


class WebRenderError(ValueError):
    """工作区网页渲染不符合安全限制。"""


_ACTIVE_OR_REMOTE = re.compile(
    r"<\s*(?:script|iframe|object|embed)\b|(?:src|href)\s*=\s*[\"']?https?://|"
    r"url\s*\(\s*[\"']?https?://",
    re.IGNORECASE,
)


class WorkspaceWebRenderer:
    """仅渲染本地静态 HTML，拒绝脚本与远程资源加载。"""

    def __init__(self, workspace: AgentWorkspace) -> None:
        self.workspace = workspace

    def validate(self, source: str, output: str) -> tuple[Path, Path]:
        try:
            html_path = self.workspace.resolve_relative(source)
            image_path = self.workspace.resolve_relative(output)
        except WorkspaceError as error:
            raise WebRenderError(str(error)) from error
        if html_path.suffix.casefold() not in {".html", ".htm"}:
            raise WebRenderError("待渲染文件必须是工作区内的 HTML 文件。")
        if image_path.suffix.casefold() != ".png":
            raise WebRenderError("截图输出文件必须使用 .png 后缀。")
        if not html_path.is_file():
            raise WebRenderError("待渲染 HTML 文件不存在。")
        return html_path, image_path

    async def render(self, source: str, output: str) -> tuple[str, bytes]:
        html_path, image_path = self.validate(source, output)
        try:
            content = html_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise WebRenderError("待渲染 HTML 必须是 UTF-8 文本。") from error
        if _ACTIVE_OR_REMOTE.search(content):
            raise WebRenderError("静态网页截图不允许脚本、嵌入页面或远程 HTTP 资源。")
        from nonebot_plugin_htmlkit import html_to_pic

        image = await html_to_pic(
            content,
            dpi=96,
            max_width=960,
            device_height=640,
            default_font_size=16,
            allow_refit=False,
        )
        try:
            self.workspace.write_bytes(image_path.relative_to(self.workspace.root).as_posix(), image)
        except WorkspaceError as error:
            raise WebRenderError(str(error)) from error
        return image_path.relative_to(self.workspace.root).as_posix(), image
