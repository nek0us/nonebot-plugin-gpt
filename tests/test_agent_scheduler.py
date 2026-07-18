import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


PACKAGE_PATH = Path(__file__).parents[1] / "nonebot_plugin_gpt"
package = types.ModuleType("nonebot_plugin_gpt")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("nonebot_plugin_gpt", package)
agent_scheduler = importlib.import_module("nonebot_plugin_gpt.agent_scheduler")


class AgentSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_persists_and_delivers_due_item(self):
        delivered = []
        now = [100.0]

        async def handler(item):
            delivered.append(item)

        with TemporaryDirectory() as temporary:
            scheduler = agent_scheduler.AgentScheduler(
                Path(temporary) / "reminders.json",
                handler,
                clock=lambda: now[0],
            )
            item = await scheduler.schedule(
                delay_seconds=1,
                target={"adapter": "Console", "id": "user"},
                conversation_session_id="console:private:user",
                conversation_user_id="console:user",
                user_id="user",
                content="喝水",
            )
            self.assertEqual((await scheduler.list())[0].id, item.id)

            now[0] = 102.0
            due = await scheduler._take_due()
            for value in due:
                await handler(value)

            self.assertEqual([value.content for value in delivered], ["喝水"])
            self.assertEqual(await scheduler.list(), [])

    async def test_failed_delivery_is_retried_at_most_twice(self):
        with TemporaryDirectory() as temporary:
            scheduler = agent_scheduler.AgentScheduler(Path(temporary) / "reminders.json", lambda _: asyncio.sleep(0))
            item = agent_scheduler.ScheduledReminder(
                id="reminder_test",
                due_at=0,
                target={"adapter": "Console", "id": "user"},
                conversation_session_id="console:private:user",
                conversation_user_id="console:user",
                user_id="user",
                content="测试",
                attempts=2,
            )
            await scheduler._retry(item)
            self.assertEqual(await scheduler.list(), [])
