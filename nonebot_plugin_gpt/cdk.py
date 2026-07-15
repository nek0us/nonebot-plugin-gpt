"""跨平台白名单 CDK 的创建、兑换与旧数据迁移。"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GrantTarget = Callable[[str], Awaitable[str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback.copy()
    return value if isinstance(value, dict) else fallback.copy()


class CdkRegistry:
    """管理一次性兑换码及其可审计的授权来源。"""

    def __init__(
        self,
        path: Path,
        *,
        legacy_list_path: Path | None = None,
        legacy_source_path: Path | None = None,
    ) -> None:
        self.path = path
        self.legacy_list_path = legacy_list_path
        self.legacy_source_path = legacy_source_path
        self._lock = asyncio.Lock()
        self._migrate_legacy_once()

    def _load(self) -> dict[str, Any]:
        state = _read_json(self.path, {"version": 2, "codes": {}, "migration": {}})
        codes = state.get("codes")
        if not isinstance(codes, dict):
            state["codes"] = {}
        migration = state.get("migration")
        if not isinstance(migration, dict):
            state["migration"] = {}
        state["version"] = 2
        return state

    def _write(self, state: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _migrate_legacy_once(self) -> None:
        state = self._load()
        migration = state["migration"]
        if migration.get("legacy_cdk_v1"):
            return

        legacy_codes = (
            _read_json(self.legacy_list_path, {})
            if self.legacy_list_path and self.legacy_list_path.exists()
            else {}
        )
        legacy_sources = (
            _read_json(self.legacy_source_path, {})
            if self.legacy_source_path and self.legacy_source_path.exists()
            else {}
        )
        imported_available = 0
        imported_unresolved = 0
        codes = state["codes"]
        for raw_code, legacy_target in legacy_codes.items():
            if not isinstance(raw_code, str) or not raw_code.strip():
                continue
            code = raw_code.strip().lower()
            if code in codes:
                continue
            note = legacy_sources.get(raw_code, "")
            record: dict[str, Any] = {
                "created_at": _now(),
                "created_by": "legacy-v1",
                "created_scope": "",
                "note": str(note) if note else "",
                "migrated_from": "legacy-v1",
            }
            if legacy_target in (None, ""):
                record["status"] = "available"
                imported_available += 1
            else:
                # 旧 QQ 实现仅保存裸 group/guild ID，缺少适配器命名空间，
                # 不能安全推导为当前跨平台会话标识。
                record.update({
                    "status": "legacy_redeemed_unresolved",
                    "legacy_target": str(legacy_target),
                })
                imported_unresolved += 1
            codes[code] = record

        migration["legacy_cdk_v1"] = {
            "completed_at": _now(),
            "available": imported_available,
            "redeemed_unresolved": imported_unresolved,
        }
        self._write(state)

    async def create(
        self,
        *,
        note: str,
        creator_id: str,
        creator_scope: str,
        grant_kind: str = "scope",
    ) -> str:
        if grant_kind not in {"scope", "participant"}:
            raise ValueError("unsupported CDK grant kind")
        async with self._lock:
            state = self._load()
            codes = state["codes"]
            while True:
                code = secrets.token_hex(8)
                if code not in codes:
                    break
            codes[code] = {
                "status": "available",
                "created_at": _now(),
                "created_by": creator_id,
                "created_scope": creator_scope,
                "note": note.strip(),
                "grant_kind": grant_kind,
            }
            self._write(state)
            return code

    async def redeem(
        self,
        code: str,
        *,
        redeemer_id: str,
        scope_id: str,
        grant_scope: GrantTarget,
        participant_id: str = "",
        grant_participant: GrantTarget | None = None,
    ) -> str:
        normalized = code.strip().lower()
        if not normalized:
            return "请提供 CDK。"
        async with self._lock:
            state = self._load()
            record = state["codes"].get(normalized)
            if not isinstance(record, dict):
                return "CDK 不存在或已失效。"
            status = record.get("status")
            if status == "redeemed":
                return "该 CDK 已被兑换。"
            if status == "revoked":
                return "该 CDK 已被作废。"
            if status == "legacy_redeemed_unresolved":
                return "该旧 CDK 已使用，且旧目标无法安全迁移；请联系管理员重新生成 CDK。"
            if status != "available":
                return "该 CDK 当前不可兑换。"

            grant_kind = str(record.get("grant_kind") or "scope")
            if grant_kind == "participant":
                if not participant_id or grant_participant is None:
                    return "当前会话无法识别兑换者，个人 CDK 兑换未完成。"
                grant_target = participant_id
                grant_callback = grant_participant
                success_text = "兑换成功，当前用户已获得同一适配器全部会话的聊天权限。"
            else:
                grant_target = scope_id
                grant_callback = grant_scope
                success_text = "兑换成功，当前会话已获得聊天权限。"

            try:
                grant_result = await grant_callback(grant_target)
            except Exception:
                return "兑换未完成，请稍后重试。"
            if grant_result not in {"添加成功", "白名单已存在"}:
                return f"兑换未完成：{grant_result}"

            record.update({
                "status": "redeemed",
                "redeemed_at": _now(),
                "redeemed_by": redeemer_id,
                "redeemed_scope": scope_id,
                "redeemed_target": grant_target,
            })
            self._write(state)
            note = str(record.get("note") or "")
            source = f"（来源：{note}）" if note else ""
            return f"{success_text}{source}"

    async def revoke(self, code: str, *, operator_id: str) -> str:
        normalized = code.strip().lower()
        async with self._lock:
            state = self._load()
            record = state["codes"].get(normalized)
            if not isinstance(record, dict):
                return "CDK 不存在。"
            if record.get("status") == "redeemed":
                kind = str(record.get("grant_kind") or "scope")
                command = "退出个人白名单" if kind == "participant" else "删除白名单"
                return f"该 CDK 已兑换，不能作废；请使用“{command}”撤销对应权限。"
            if record.get("status") == "revoked":
                return "该 CDK 已作废。"
            record.update({
                "status": "revoked",
                "revoked_at": _now(),
                "revoked_by": operator_id,
            })
            self._write(state)
            return "CDK 已作废。"

    def format_list(self) -> str:
        state = self._load()
        codes = state["codes"]
        if not codes:
            return "暂无 CDK。"
        lines = ["CDK 列表"]
        for code, record in sorted(codes.items()):
            if not isinstance(record, dict):
                continue
            status = str(record.get("status", "unknown"))
            note = str(record.get("note") or "未备注")
            created = str(record.get("created_at") or "未知时间")
            kind = "个人" if str(record.get("grant_kind") or "scope") == "participant" else "会话"
            if status == "redeemed":
                target = str(record.get("redeemed_target") or record.get("redeemed_scope") or "未知范围")
                lines.append(f"{code}：已兑换（{kind}） -> {target}；来源：{note}；创建：{created}")
            elif status == "available":
                lines.append(f"{code}：待兑换（{kind}）；来源：{note}；创建：{created}")
            elif status == "legacy_redeemed_unresolved":
                target = str(record.get("legacy_target") or "未知旧目标")
                lines.append(f"{code}：旧版已兑换待确认 -> {target}；来源：{note}")
            else:
                lines.append(f"{code}：已作废；来源：{note}")
        return "\n".join(lines)

    def list_records(self) -> list[dict[str, str]]:
        """返回供管理视图表格使用的非敏感 CDK 元数据。"""
        records: list[dict[str, str]] = []
        for code, record in sorted(self._load()["codes"].items()):
            if not isinstance(record, dict):
                continue
            records.append({
                "code": str(code),
                "status": str(record.get("status") or "unknown"),
                "grant_kind": str(record.get("grant_kind") or "scope"),
                "note": str(record.get("note") or ""),
                "created_at": str(record.get("created_at") or ""),
            })
        return records

    def migration_summary(self) -> str:
        migration = self._load()["migration"].get("legacy_cdk_v1", {})
        available = int(migration.get("available", 0))
        unresolved = int(migration.get("redeemed_unresolved", 0))
        return f"旧 CDK 迁移：待兑换 {available} 个，已兑换待确认 {unresolved} 个。"
