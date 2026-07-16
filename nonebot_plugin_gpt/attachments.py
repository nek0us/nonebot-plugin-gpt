"""从适配器消息中提取可上传给 ChatGPT 的图片附件。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from ChatGPTWeb.config import IOFile
from nonebot import get_driver
from nonebot.internal.driver import HTTPClientMixin, Request
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import Image, UniMessage


async def extract_image_files(message, *, proxy: str = "") -> list[IOFile]:
    """从 UniMessage 或原始消息段提取可上传的图片附件。"""
    files: list[IOFile] = []
    urls: list[str] = []
    seen_urls: set[str] = set()

    if isinstance(message, UniMessage):
        unified = message
    else:
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
    if not urls:
        return files

    driver = get_driver()
    if not isinstance(driver, HTTPClientMixin):
        logger.warning("当前 NoneBot 驱动器不支持 HTTP 客户端，已跳过远程图片下载")
        return files

    async with driver.get_session(proxy=proxy or None) as client:
        for url in urls:
            try:
                response = await client.request(Request("GET", url, timeout=30))
            except Exception:
                logger.debug(f"下载聊天图片失败，已跳过：{url}")
                continue
            if response.status_code < 200 or response.status_code >= 300:
                logger.debug(f"下载聊天图片返回异常状态码，已跳过：{response.status_code}")
                continue
            if not isinstance(response.content, bytes):
                continue
            name = PurePosixPath(url.split("?", maxsplit=1)[0]).name or "image"
            files.append(IOFile(content=response.content, name=name))
    return files
