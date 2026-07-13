"""人设存储的适配器无关操作。"""

from __future__ import annotations

import json

from ChatGPTWeb import chatgpt

from .source import personpath


async def ensure_default_persona(chatbot: chatgpt) -> None:
    """确保内置默认人设存在，并同步其权限元数据。"""
    persona = {
        "name": "默认",
        "r18": False,
        "open": "",
        "value": "你好",
    }
    metadata = json.loads(personpath.read_text(encoding="utf-8"))
    if persona["name"] not in metadata:
        await chatbot.add_personality(persona)
    metadata[persona["name"]] = {
        "r18": persona["r18"],
        "open": persona["open"],
    }
    personpath.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
