"""从适配器消息中提取可上传给 ChatGPT 的图片附件。"""

from __future__ import annotations

from pathlib import PurePosixPath

from ChatGPTWeb.config import IOFile
from httpx import AsyncClient


async def extract_image_files(message, *, proxy: str = "") -> list[IOFile]:
    """提取带有 HTTP URL 的图片消息段；不支持的段会被安全跳过。"""
    urls = []
    for segment in message:
        if getattr(segment, "type", "") != "image":
            continue
        data = getattr(segment, "data", {})
        url = data.get("url") if isinstance(data, dict) else None
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            urls.append(url)
    if not urls:
        return []

    files = []
    async with AsyncClient(proxy=proxy or None) as client:
        for url in urls:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception:
                continue
            name = PurePosixPath(url.split("?", maxsplit=1)[0]).name or "image"
            files.append(IOFile(content=response.content, name=name))
    return files
