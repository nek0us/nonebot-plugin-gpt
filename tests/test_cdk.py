import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt" / "cdk.py"
_SPEC = importlib.util.spec_from_file_location("cdk_under_test", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
CdkRegistry = _MODULE.CdkRegistry


class CdkRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_redeem_grants_the_current_cross_platform_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CdkRegistry(Path(directory) / "codes.json")
            code = await registry.create(
                note="测试来源",
                creator_id="admin",
                creator_scope="onebot.v11:group:1",
            )
            granted = []

            async def grant(scope_id: str) -> str:
                granted.append(scope_id)
                return "添加成功"

            result = await registry.redeem(
                code.upper(),
                redeemer_id="member",
                scope_id="satori:channel:room",
                grant_scope=grant,
            )

            self.assertEqual(granted, ["satori:channel:room"])
            self.assertIn("兑换成功", result)
            self.assertIn("测试来源", result)
            self.assertEqual(
                await registry.redeem(
                    code,
                    redeemer_id="other",
                    scope_id="onebot.v11:group:2",
                    grant_scope=grant,
                ),
                "该 CDK 已被兑换。",
            )

    async def test_legacy_unused_codes_remain_redeemable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_codes = root / "cdklist.json"
            legacy_sources = root / "cdksource.json"
            legacy_codes.write_text(json.dumps({"legacy-code": None, "used": "123"}), encoding="utf-8")
            legacy_sources.write_text(json.dumps({"legacy-code": "旧来源", "used": "旧群"}), encoding="utf-8")
            registry = CdkRegistry(
                root / "codes.json",
                legacy_list_path=legacy_codes,
                legacy_source_path=legacy_sources,
            )

            async def grant(_scope_id: str) -> str:
                return "白名单已存在"

            self.assertIn(
                "兑换成功",
                await registry.redeem(
                    "legacy-code",
                    redeemer_id="member",
                    scope_id="onebot.v11:group:1",
                    grant_scope=grant,
                ),
            )
            self.assertEqual(
                await registry.redeem(
                    "used",
                    redeemer_id="member",
                    scope_id="onebot.v11:group:1",
                    grant_scope=grant,
                ),
                "该旧 CDK 已使用，且旧目标无法安全迁移；请联系管理员重新生成 CDK。",
            )

    async def test_personal_cdk_grants_the_redeemer_not_the_current_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CdkRegistry(Path(directory) / "codes.json")
            code = await registry.create(
                note="个人测试",
                creator_id="admin",
                creator_scope="onebot.v11:group:1",
                grant_kind="participant",
            )
            granted_scopes = []
            granted_users = []

            async def grant_scope(scope_id: str) -> str:
                granted_scopes.append(scope_id)
                return "添加成功"

            async def grant_user(identity: str) -> str:
                granted_users.append(identity)
                return "添加成功"

            result = await registry.redeem(
                code,
                redeemer_id="42",
                scope_id="onebot.v11:group:99",
                grant_scope=grant_scope,
                participant_id="onebot.v11:user:42",
                grant_participant=grant_user,
            )

            self.assertEqual(granted_scopes, [])
            self.assertEqual(granted_users, ["onebot.v11:user:42"])
            self.assertIn("同一适配器全部会话", result)
            self.assertIn("已兑换（个人）", registry.format_list())

    async def test_revoked_code_cannot_be_redeemed(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CdkRegistry(Path(directory) / "codes.json")
            code = await registry.create(
                note="",
                creator_id="admin",
                creator_scope="onebot.v11:group:1",
            )
            self.assertEqual(await registry.revoke(code, operator_id="admin"), "CDK 已作废。")

            async def grant(_scope_id: str) -> str:
                self.fail("作废 CDK 不应再调用白名单授权")

            self.assertEqual(
                await registry.redeem(
                    code,
                    redeemer_id="member",
                    scope_id="satori:channel:room",
                    grant_scope=grant,
                ),
                "该 CDK 已被作废。",
            )

    async def test_lists_show_newest_cdk_first(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = CdkRegistry(Path(directory) / "codes.json")
            state = registry._load()
            state["codes"] = {
                "old": {"status": "available", "created_at": "2026-01-01T00:00:00+00:00"},
                "new": {"status": "available", "created_at": "2026-01-02T00:00:00+00:00"},
            }
            registry._write(state)

            self.assertEqual(registry.list_records()[0]["code"], "new")
            self.assertLess(registry.format_list().index("new"), registry.format_list().index("old"))
