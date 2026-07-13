"""从适配器消息中提取可上传给 ChatGPT 的图片附件。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from ChatGPTWeb.config import IOFile
from httpx import AsyncClient
from nonebot_plugin_alconna.uniseg import Image, UniMessage


async def extract_image_files(message, *, proxy: str = "") -> list[IOFile]:
    """从 UniMessage 或原始消息段提取可上传的图片附件。"""
    files: list[IOFile] = []
    urls: list[str] = []
    seen_urls: set[str] = set()

    try:
        unified = UniMessage.of(message)
    except Exception:
        unified = UniMessage()
    for segment in unified:
        if not isinstance(segment, Image):
            continue
        if segment.raw:
            try:
                files.append(IOFile(content=segment.raw_bytes, name=segment.name))
            except ValueError:
                pass
        elif segment.path:
            try:
                path = Path(segment.path)
                files.append(IOFile(content=path.read_bytes(), name=segment.name or path.name))
            except OSError:
                pass
        elif segment.url:
            urls.append(segment.url)

    for segment in message:
        if getattr(segment, "type", "") != "image":
            continue
        data = getattr(segment, "data", {})
        url = data.get("url") if isinstance(data, dict) else None
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            urls.append(url)
    urls = [url for url in urls if not (url in seen_urls or seen_urls.add(url))]
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
