"""将核心存储重构前的人设正文迁入新版运行目录。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_legacy_personas(path: Path) -> list[dict[str, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    personas: list[dict[str, str]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].strip()
            and isinstance(item.get("value"), str)
        ):
            personas.append({"name": item["name"], "value": item["value"]})
    return personas


def migrate_legacy_personas(data_dir: Path) -> list[dict[str, str]]:
    """合并旧 ``personality`` 文件，返回本次可用的人设正文。"""
    legacy_path = data_dir / "personality"
    target_path = data_dir / "chatgptweb" / "personas.json"
    legacy = _read_legacy_personas(legacy_path)
    try:
        current_raw: Any = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current_raw = {}
    current_values = current_raw.get("personas", []) if isinstance(current_raw, dict) else []
    current = [
        {"name": item["name"], "value": item["value"]}
        for item in current_values
        if (
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].strip()
            and isinstance(item.get("value"), str)
        )
    ]
    merged = {item["name"]: item for item in legacy}
    merged.update({item["name"]: item for item in current})
    values = list(merged.values())
    needs_cleanup = values != current_values
    if legacy or needs_cleanup:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps({"version": 2, "personas": values}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return values
