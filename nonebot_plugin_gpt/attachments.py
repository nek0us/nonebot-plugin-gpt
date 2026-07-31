"""从适配器消息中提取可上传给 ChatGPT 的附件。"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import unquote, urljoin, urlsplit

import aiohttp
from ChatGPTWeb.config import IOFile
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import Audio, File, Image, UniMessage, Video, Voice


_NON_IMAGE_UPLOAD_SEGMENTS = (Audio, File, Video, Voice)
_GENERIC_NAMES = {"", "image", "attachment", "file"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class AttachmentDownloadError(RuntimeError):
    """远程附件因安全限制或下载异常而不可用。"""


def _safe_filename(value: str, fallback: str = "attachment") -> str:
    name = PurePosixPath(unquote(str(value)).replace("\\", "/")).name
    name = "".join(
        "_" if char in _INVALID_FILENAME_CHARS or ord(char) < 32 else char
        for char in name
    ).strip(" .")
    if name in {"", ".", ".."}:
        name = fallback
    return name[:255]


def _segment_name(segment, fallback: str) -> str:
    return _safe_filename(str(getattr(segment, "name", "") or fallback), fallback)


def _current_total_size(files: Iterable[IOFile]) -> int:
    return sum(len(item.content) for item in files)


def _append_content(
    files: list[IOFile],
    content: bytes,
    name: str,
    *,
    max_file_size: int,
    max_total_size: int,
    max_count: int,
) -> bool:
    safe_name = _safe_filename(name)
    if len(files) >= max_count:
        logger.warning(f"聊天附件数量超过限制 {max_count}，已跳过 {safe_name}")
        return False
    if len(content) > max_file_size:
        logger.warning(f"聊天附件 {safe_name} 超过单文件大小限制，已跳过")
        return False
    if _current_total_size(files) + len(content) > max_total_size:
        logger.warning(f"聊天附件 {safe_name} 会超过本条消息总大小限制，已跳过")
        return False
    files.append(IOFile(content=content, name=safe_name))
    return True


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _read_local_attachment(
    path_value,
    *,
    allowed_roots: Iterable[Path | str],
    max_file_size: int,
) -> tuple[bytes, str] | None:
    roots: list[Path] = []
    for value in allowed_roots:
        try:
            roots.append(Path(value).expanduser().resolve(strict=True))
        except OSError:
            continue
    if not roots:
        logger.warning("附件包含本地路径，但未配置可信本地附件目录，已跳过")
        return None
    try:
        source = Path(path_value).expanduser()
        resolved = source.resolve(strict=True)
        if not resolved.is_file() or not any(_is_within(resolved, root) for root in roots):
            logger.warning("附件本地路径不在可信目录内，已跳过")
            return None
        if resolved.stat().st_size > max_file_size:
            logger.warning(f"聊天附件 {resolved.name} 超过单文件大小限制，已跳过")
            return None
        with resolved.open("rb") as file:
            content = file.read(max_file_size + 1)
        if len(content) > max_file_size:
            logger.warning(f"聊天附件 {resolved.name} 超过单文件大小限制，已跳过")
            return None
        return content, resolved.name
    except OSError:
        logger.warning("读取本地聊天附件失败，已跳过")
        return None


def _extract_segment(
    segment,
    files: list[IOFile],
    remote_files: list[tuple[str, str]],
    *,
    allowed_local_roots: Iterable[Path | str],
    max_file_size: int,
    max_total_size: int,
    max_count: int,
) -> None:
    name = _segment_name(segment, "attachment")
    if getattr(segment, "raw", None):
        try:
            _append_content(
                files,
                segment.raw_bytes,
                name,
                max_file_size=max_file_size,
                max_total_size=max_total_size,
                max_count=max_count,
            )
        except ValueError:
            return
    elif getattr(segment, "path", None):
        local = _read_local_attachment(
            segment.path,
            allowed_roots=allowed_local_roots,
            max_file_size=max_file_size,
        )
        if local is None:
            return
        content, path_name = local
        _append_content(
            files,
            content,
            name if name != "attachment" else path_name,
            max_file_size=max_file_size,
            max_total_size=max_total_size,
            max_count=max_count,
        )
    elif getattr(segment, "url", None):
        remote_files.append((str(segment.url), name))


def _normalized_hosts(values: Iterable[str]) -> set[str]:
    return {
        str(value).strip().lower().rstrip(".")
        for value in values
        if str(value).strip()
    }


def _address_is_public(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


async def _resolve_host_addresses(host: str, port: int) -> set[str]:
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
    )
    return {str(record[4][0]).split("%", maxsplit=1)[0] for record in records}


async def _validate_remote_url(
    url: str,
    *,
    allow_private_urls: bool,
    allowed_hosts: Iterable[str],
) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise AttachmentDownloadError("URL 格式无效") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise AttachmentDownloadError("只允许 HTTP 或 HTTPS 地址")
    if parsed.username is not None or parsed.password is not None:
        raise AttachmentDownloadError("URL 不允许包含登录凭据")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise AttachmentDownloadError("URL 缺少主机名")
    if allow_private_urls or host in _normalized_hosts(allowed_hosts):
        return
    try:
        addresses = {str(ipaddress.ip_address(host))}
    except ValueError:
        try:
            addresses = await _resolve_host_addresses(host, port)
        except OSError as exc:
            raise AttachmentDownloadError("无法解析附件主机") from exc
    if not addresses or any(not _address_is_public(address) for address in addresses):
        raise AttachmentDownloadError("目标地址属于本机、内网或保留网段")


def _url_label(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.hostname or 'unknown'}{parsed.path or '/'}"


async def _download_remote_file(
    session: aiohttp.ClientSession,
    url: str,
    *,
    proxy: str,
    allow_private_urls: bool,
    allowed_hosts: Iterable[str],
    max_file_size: int,
    remaining_total_size: int,
    max_redirects: int,
) -> tuple[bytes, str] | None:
    current_url = url
    for redirect_count in range(max_redirects + 1):
        await _validate_remote_url(
            current_url,
            allow_private_urls=allow_private_urls,
            allowed_hosts=allowed_hosts,
        )
        async with session.get(
            current_url,
            allow_redirects=False,
            proxy=proxy or None,
        ) as response:
            if response.status in _REDIRECT_STATUSES:
                location = response.headers.get("Location", "").strip()
                if not location:
                    raise AttachmentDownloadError("重定向响应缺少目标地址")
                if redirect_count >= max_redirects:
                    raise AttachmentDownloadError("重定向次数超过限制")
                current_url = urljoin(current_url, location)
                continue
            if response.status < 200 or response.status >= 300:
                raise AttachmentDownloadError(f"远程服务器返回 HTTP {response.status}")
            content_length = response.content_length
            effective_limit = min(max_file_size, remaining_total_size)
            if effective_limit <= 0:
                raise AttachmentDownloadError("本条消息附件总大小已达上限")
            if content_length is not None and content_length > effective_limit:
                raise AttachmentDownloadError("远程附件超过大小限制")
            content = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                content.extend(chunk)
                if len(content) > effective_limit:
                    raise AttachmentDownloadError("远程附件超过大小限制")
            disposition_name = (
                response.content_disposition.filename
                if response.content_disposition is not None
                else ""
            )
            url_name = PurePosixPath(urlsplit(current_url).path).name
            return bytes(content), _safe_filename(disposition_name or url_name)
    return None


async def extract_upload_files(
    message,
    *,
    proxy: str = "",
    upload_images: bool,
    upload_files: bool,
    max_file_size: int,
    max_total_size: int | None = None,
    max_count: int = 8,
    allowed_local_roots: Iterable[Path | str] = (),
    allow_private_urls: bool = False,
    allowed_hosts: Iterable[str] = (),
    download_timeout: int = 30,
    max_redirects: int = 3,
) -> list[IOFile]:
    """提取跨平台附件并在安全限制内下载为 ChatGPT 可上传文件。"""
    if max_total_size is None:
        max_total_size = max_file_size * 2
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
            allowed_local_roots=allowed_local_roots,
            max_file_size=max_file_size,
            max_total_size=max_total_size,
            max_count=max_count,
        )

    for segment in message if hasattr(message, "__iter__") else ():
        if not upload_images or getattr(segment, "type", "") != "image":
            continue
        data = getattr(segment, "data", {})
        url = data.get("url") if isinstance(data, dict) else None
        if isinstance(url, str):
            remote_files.append((url, "image"))

    remote_files = [
        (url, name)
        for url, name in remote_files
        if not (url in seen_urls or seen_urls.add(url))
    ]
    if not remote_files or len(files) >= max_count:
        return files

    timeout = aiohttp.ClientTimeout(total=download_timeout)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for url, configured_name in remote_files[: max_count - len(files)]:
            try:
                downloaded = await _download_remote_file(
                    session,
                    url,
                    proxy=proxy,
                    allow_private_urls=allow_private_urls,
                    allowed_hosts=allowed_hosts,
                    max_file_size=max_file_size,
                    remaining_total_size=max_total_size - _current_total_size(files),
                    max_redirects=max_redirects,
                )
            except AttachmentDownloadError as exc:
                logger.warning(f"聊天附件下载已跳过（{_url_label(url)}）：{exc}")
                continue
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning(
                    f"聊天附件下载失败（{_url_label(url)}）：{type(exc).__name__}"
                )
                continue
            if downloaded is None:
                continue
            content, remote_name = downloaded
            name = configured_name if configured_name not in _GENERIC_NAMES else remote_name
            _append_content(
                files,
                content,
                name,
                max_file_size=max_file_size,
                max_total_size=max_total_size,
                max_count=max_count,
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
