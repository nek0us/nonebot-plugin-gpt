"""从适配器消息中提取可上传给 ChatGPT 的图片附件。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from ChatGPTWeb.config import IOFile
from nonebot import get_driver
from nonebot.internal.driver import HTTPClientMixin, Request
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import Audio, File, Image, UniMessage, Video, Voice


_NON_IMAGE_UPLOAD_SEGMENTS = (Audio, File, Video, Voice)


def _append_content(
    files: list[IOFile],
    content: bytes,
    name: str,
    *,
    max_file_size: int,
) -> None:
    if len(content) > max_file_size:
        logger.warning(f"聊天附件 {name} 超过大小限制，已跳过")
        return
    files.append(IOFile(content=content, name=name))


def _segment_name(segment, fallback: str) -> str:
    return str(getattr(segment, "name", "") or fallback)


def _extract_segment(
    segment,
    files: list[IOFile],
    remote_files: list[tuple[str, str]],
    *,
    max_file_size: int,
) -> None:
    name = _segment_name(segment, "attachment")
    if getattr(segment, "raw", None):
        try:
            _append_content(
                files,
                segment.raw_bytes,
                name,
                max_file_size=max_file_size,
            )
        except ValueError:
            return
    elif getattr(segment, "path", None):
        try:
            path = Path(segment.path)
            _append_content(
                files,
                path.read_bytes(),
                name if name != "attachment" else path.name,
                max_file_size=max_file_size,
            )
        except OSError:
            return
    elif getattr(segment, "url", None):
        remote_files.append((str(segment.url), name))


async def extract_upload_files(
    message,
    *,
    proxy: str = "",
    upload_images: bool,
    upload_files: bool,
    max_file_size: int,
) -> list[IOFile]:
    """提取跨平台附件并在允许时下载为 ChatGPT 可上传的文件。"""
    files: list[IOFile] = []
    remote_files: list[tuple[str, str]] = []
    seen_urls: set[str] = set()


    if isinstance(message, UniMessage):
        unified = message
    else:
        try:
            unified = UniMessage.of(message)
        except Exception:
            unified = UniMessage()
    for segment in unified:
        is_image = isinstance(segment, Image)
        is_file = isinstance(segment, _NON_IMAGE_UPLOAD_SEGMENTS)
        if not (upload_images and is_image) and not (upload_files and is_file):
            continue
        _extract_segment(
            segment,
            files,
            remote_files,
            max_file_size=max_file_size,
        )

    for segment in message if hasattr(message, "__iter__") else ():
        if not upload_images or getattr(segment, "type", "") != "image":
            continue
        data = getattr(segment, "data", {})
        url = data.get("url") if isinstance(data, dict) else None
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            remote_files.append((url, "image"))

    remote_files = [
        (url, name)
        for url, name in remote_files
        if url.startswith(("http://", "https://"))
        and not (url in seen_urls or seen_urls.add(url))
    ]
    if not remote_files:
        return files

    driver = get_driver()
    if not isinstance(driver, HTTPClientMixin):
        logger.warning("当前 NoneBot 驱动器不支持 HTTP 客户端，已跳过远程图片下载")
        return files

    async with driver.get_session(proxy=proxy or None) as client:
        for url, configured_name in remote_files:
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
            url_name = PurePosixPath(url.split("?", maxsplit=1)[0]).name
            name = configured_name if configured_name not in {"", "image", "attachment"} else url_name
            _append_content(
                files,
                response.content,
                name or "attachment",
                max_file_size=max_file_size,
            )
    return files


async def extract_image_files(message, *, proxy: str = "") -> list[IOFile]:
    """兼容旧调用：仅提取图片，不上传普通文件。"""
    return await extract_upload_files(
        message,
        proxy=proxy,
        upload_images=True,
        upload_files=False,
        max_file_size=20 * 1024 * 1024,
    )
