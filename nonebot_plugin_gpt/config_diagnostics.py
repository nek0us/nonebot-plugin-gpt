"""Diagnostics for silent dotenv configuration overrides."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any, Iterable


_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$"
)
_SENSITIVE_PARTS = ("key", "password", "secret", "session", "token", "proxy")


def _env_paths(value: Any) -> list[Path]:
    if value is None:
        return []
    values: Iterable[Any] = value if isinstance(value, (list, tuple)) else (value,)
    return [Path(item).expanduser() for item in values if str(item).strip()]


def _display_value(key: str, value: str) -> str:
    if any(part in key.casefold() for part in _SENSITIVE_PARTS):
        return "<已隐藏>"
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in "\"'":
        normalized = normalized[1:-1]
    return normalized[:80]


def _normalized_value(value: str) -> str:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in "\"'":
        normalized = normalized[1:-1]
    return normalized.casefold()


def find_conflicting_gpt_settings(env_files: Any) -> list[dict[str, Any]]:
    """Return conflicting ``gpt_*`` assignments in effective dotenv order."""
    conflicts: list[dict[str, Any]] = []
    assignments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in _env_paths(env_files):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        resolved = str(path.resolve())
        for line_number, line in enumerate(lines, start=1):
            match = _ASSIGNMENT.match(line)
            if not match:
                continue
            key = match.group("key").casefold()
            if not key.startswith("gpt_"):
                continue
            value = match.group("value").strip()
            assignments[key].append({
                "file": resolved,
                "line": line_number,
                "raw_value": value,
                "value": _display_value(key, value),
                "normalized_value": _normalized_value(value),
            })
    for key, values in assignments.items():
        distinct = {item["normalized_value"] for item in values}
        if len(values) < 2 or len(distinct) < 2:
            continue
        public_values = [
            {
                "file": item["file"],
                "line": item["line"],
                "value": item["value"],
            }
            for item in values
        ]
        effective = values[-1]
        conflicts.append({
            "file": effective["file"],
            "key": key,
            "assignments": public_values,
            "effective_file": effective["file"],
            "effective_line": effective["line"],
            "effective_value": effective["value"],
        })
    return conflicts


def log_conflicting_gpt_settings(config: Any, logger: Any) -> list[dict[str, Any]]:
    """Log actionable line-level warnings after NoneBot resolves its env files."""
    conflicts = find_conflicting_gpt_settings(getattr(config, "_env_file", None))
    for item in conflicts:
        assignments = "，".join(
            f"{value['file']}:{value['line']}={value['value']}"
            for value in item["assignments"]
        )
        logger.warning(
            "环境配置冲突：{} 被重复设置（{}）；"
            "最终生效的是 {}:{}={}，请删除旧项以免能力被静默覆盖",
            item["key"],
            assignments,
            item["effective_file"],
            item["effective_line"],
            item["effective_value"],
        )
    return conflicts
