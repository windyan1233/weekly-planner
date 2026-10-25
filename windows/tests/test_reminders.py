"""提醒测试：默认 24 小时规则、多提醒、完成取消、改期重算、错过补发、
逾期只提醒一次、稍后提醒、睡眠恢复与系统时间跳变、通知通道。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support import TestEnv, qapp  # noqa: E402

from src.models import PlanDraft, TaskDraft  # noqa: E402
from src.notification_manager import (  # noqa: E402
    NotificationManager,
    build_toast_script,
    build_toast_xml,
)
from src.reminder_scheduler import (  # noqa: E402
    FiredReminder,
    ReminderEngine,
    ReminderMessage,
    ReminderScheduler,
    compose_message,
    compute_due_reminder,
)
from src.settings_store import ReminderPolicy  # noqa: E402
from src.time_utils import (  # noqa: E402
    MODE_BEFORE_DUE_24H,
    MODE_PREVIOUS_DAY_AT,
    due_reminder_time,
    format_dt,
)

NOW = datetime.now().replace(second=0, microsecond=0)


def rounded(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


class DueReminderComputationTest(unittest.TestCase):
    """截止前一天提醒的时间计算。"""

    def test_default_mode_is_24_hours_before(self) -> None:
        due = datetime(2026, 10, 25, 18, 0)
        fire = compute_due_reminder(due, ReminderPolicy())
        self.assertEqual(fire, datetime(2026, 10, 24, 18, 0))
        self.assertEqual((due - fire), timedelta(hours=24))

    def test_previous_day_at_given_time(self) -> None:
        due = datetime(2026, 10, 25, 18, 0)
        policy = ReminderPolicy(mode=MODE_PREVIOUS_DAY_AT, previous_day_time="09:00")
        fire = compute_due_reminder(due, policy)
        self.assertEqual(fire, datetime(2026, 10, 24, 9, 0))

    def test_previous_day_mode_handles_month_and_year_boundary(self) -> None:
        policy = ReminderPolicy(mode=MODE_PREVIOUS_DAY_AT, previous_day_time="08:30")
        fire = compute_due_reminder(datetime(2027, 1, 1, 10, 0), policy)
        self.assertEqual(fire, datetime(2026, 12, 31, 8, 30))

    def test_dst_transition_is_handled_in_absolute_time(self) -> None:
        """2026-11-01 美国夏令时结束：跨越切换点时 24 小时 ≠ 墙上时间 24 小时。"""
        new_york = ZoneInfo("America/New_York")
        due = datetime(2026, 11, 1, 12, 0)  # 切换之后（EST）
        fire = due_reminder_time(due, MODE_BEFORE_DUE_24H, tz=new_york)
        self.assertEqual(fire, datetime(2026, 10, 31, 13, 0))
        # 而「前一天指定时间」模式是纯墙上时间
        fire2 = due_reminder_time(due, MODE_PREVIOUS_DAY_AT, "09:00", tz=new_york)
        self.assertEqual(fire2, datetime(2026, 10, 31, 9, 0))


class ReminderSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("sync")

    def tearDown(self) -> None:
        self.env.close()

    def _due_rows(self, task_id: int):
        return [row for row in self.env.reminder_rows(task_id) if row.kind == "due"]

    def test_due_reminder_created_by_default(self) -> None:
        due = rounded(NOW + timedelta(days=3))
        task_id = self.env.create_task(title="默认提醒", due_at=due)
        rows = self._due_rows(task_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "pending")
        self.assertEqual(rows[0].fire_at, due - timedelta(hours=24))

    def test_can_disable_due_reminder_per_task(self) -> None:
        task_id = self.env.create_task(title="关闭提醒", due_at=NOW + timedelta(days=2), remind_due=False)
        self.assertEqual(self._due_rows(task_id), [])

    def test_plan_reminders_are_independent(self) -> None:
        due = rounded(NOW + timedelta(days=5))
        plan_a = rounded(NOW + timedelta(days=2))
        plan_b = rounded(NOW + timedelta(days=3, hours=2))
        task_id = self.env.create_task(
            title="多计划提醒",
            due_at=due,
            plans=[
                PlanDraft(plan_at=plan_a, remind_enabled=True, remind_lead_minutes=10),
                PlanDraft(plan_at=plan_b, remind_enabled=True, remind_lead_minutes=30),
                PlanDraft(plan_at=plan_b + timedelta(hours=3), remind_enabled=False),
            ],
        )
        rows = self.env.reminder_rows(task_id)
        plan_rows = [row for row in rows if row.kind == "plan"]
        self.assertEqual(len(plan_rows), 2)
        fires = sorted(row.fire_at for row in plan_rows)
        self.assertEqual(fires, [plan_a - timedelta(minutes=10), plan_b - timedelta(minutes=30)])

    def test_completing_task_cancels_pending_reminders(self) -> None:
        task_id = self.env.create_task(
            title="完成后取消",
            due_at=NOW + timedelta(days=2),
            plans=[PlanDraft(plan_at=NOW + timedelta(days=1), remind_enabled=True)],
        )
        self.assertEqual(len(self.env.reminder_rows(task_id, include_history=False)), 2)
        self.env.service.set_status(task_id, "done")
        self.assertEqual(self.env.reminder_rows(task_id, include_history=False), [])

    def test_reopening_task_restores_reminders(self) -> None:
        task_id = self.env.create_task(title="重新打开", due_at=NOW + timedelta(days=2))
        self.env.service.set_status(task_id, "done")
        self.env.service.set_status(task_id, "todo")
        self.assertEqual(len(self.env.reminder_rows(task_id, include_history=False)), 1)

    def test_changing_due_time_recalculates_reminder(self) -> None:
        task_id = self.env.create_task(title="改期", due_at=NOW + timedelta(days=2))
        original = self._due_rows(task_id)[0].fire_at

        task = self.env.service.get_task(task_id)
        draft = TaskDraft.from_task(task)
        new_due = rounded(task.due_at + timedelta(days=3))
        draft.due_at = new_due
        self.env.service.update_task(task_id, draft)

        rows = self._due_rows(task_id)
        pending = [row for row in rows if row.status == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].fire_at, new_due - timedelta(hours=24))
        self.assertNotEqual(pending[0].fire_at, original)

    def test_changing_plan_time_recalculates_only_that_reminder(self) -> None:
        due = rounded(NOW + timedelta(days=6))
        task_id = self.env.create_task(
            title="改计划时间",
            due_at=due,
            plans=[
                PlanDraft(plan_at=rounded(NOW + timedelta(days=1)), remind_enabled=True),
                PlanDraft(plan_at=rounded(NOW + timedelta(days=2)), remind_enabled=True),
            ],
        )
        task = self.env.service.get_task(task_id)
        first = task.sorted_plans()[0]
        second = task.sorted_plans()[1]
        second_fire_before = [
            row.fire_at
            for row in self.env.reminder_rows(task_id)
            if row.kind == "plan" and row.plan_id == second.id
        ][0]

        new_time = first.plan_at + timedelta(hours=3)
        self.env.service.update_plan(int(first.id or 0), plan_at=new_time)

        rows = [row for row in self.env.reminder_rows(task_id) if row.kind == "plan"]
        first_rows = [row for row in rows if row.plan_id == first.id and row.status == "pending"]
        second_rows = [row for row in rows if row.plan_id == second.id and row.status == "pending"]
        self.assertEqual(len(first_rows), 1)
        self.assertEqual(first_rows[0].fire_at, new_time - timedelta(minutes=first.remind_lead_minutes))
        self.assertEqual(len(second_rows), 1)
        self.assertEqual(second_rows[0].fire_at, second_fire_before)

    def test_setting_mode_change_rebuilds_all(self) -> None:
        due = datetime(2026, 10, 25, 18, 0)
        task_id = self.env.create_task(title="模式切换", due_at=due)
        self.assertEqual(self._due_rows(task_id)[0].fire_at, datetime(2026, 10, 24, 18, 0))

        self.env.settings.set("reminder_mode", MODE_PREVIOUS_DAY_AT)
        self.env.settings.set("previous_day_time", "09:00")
        self.env.engine.rebuild_all()
        pending = [row for row in self.env.reminder_rows(task_id) if row.status == "pending"]
        self.assertEqual(pending[0].fire_at, datetime(2026, 10, 24, 9, 0))

    def test_deleting_task_clears_reminders(self) -> None:
        task_id = self.env.create_task(title="删除清提醒", due_at=NOW + timedelta(days=2))
        self.env.service.delete_task(task_id)
        self.assertEqual(self.env.engine.reminders_for_task(task_id), [])

    def test_multiple_tasks_have_multiple_reminders(self) -> None:
        ids = [
            self.env.create_task(title=f"任务{i}", due_at=NOW + timedelta(days=i + 1))
            for i in range(3)
        ]
        self.assertEqual(len(self.env.pending()), 3)
        self.assertEqual(len({row.task_id for row in self.env.pending()}), 3)
        for task_id in ids:
            self.assertEqual(len(self.env.reminder_rows(task_id)), 1)

    def test_sync_is_idempotent(self) -> None:
        task_id = self.env.create_task(title="幂等", due_at=NOW + timedelta(days=2))
        for _ in range(3):
            self.env.engine.sync_task_by_id(task_id)
        self.assertEqual(len(self.env.reminder_rows(task_id)), 1)

    def test_skipped_reminder_is_not_recreated(self) -> None:
        """超出补发窗口的提醒标记为错过之后，重启重建不应再生成新记录。"""
        task_id = self.env.create_task(title="错过的不重建", due_at=NOW + timedelta(hours=1))
        self.assertEqual(self.env.engine.claim_due(NOW), [])
        rows = self.env.reminder_rows(task_id)
        self.assertEqual([row.status for row in rows], ["skipped"])

        self.env.engine.rebuild_all()
        self.env.reopen()
        self.env.engine.rebuild_all()
        rows = self.env.reminder_rows(task_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "skipped")
        self.assertEqual(self.env.engine.claim_due(NOW + timedelta(hours=1)), [])

    def test_sent_reminder_is_not_recreated(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        task_id = self.env.create_task(title="已发送的不重建", due_at=due)
        self.assertEqual(len(self.env.engine.claim_due(due - timedelta(hours=24))), 1)
        for _ in range(3):
            self.env.engine.rebuild_all()
        rows = self.env.reminder_rows(task_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "sent")


class ClaimTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("claim")

    def tearDown(self) -> None:
        self.env.close()

    def test_not_due_yet(self) -> None:
        due = rounded(NOW + timedelta(hours=30))
        self.env.create_task(title="还早", due_at=due)
        self.assertEqual(self.env.engine.claim_due(due - timedelta(hours=7)), [])

    def test_fires_exactly_once(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        task_id = self.env.create_task(title="准时提醒", due_at=due)
        fire_at = due - timedelta(hours=24)

        fired = self.env.engine.claim_due(fire_at)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].kind, "due")
        self.assertEqual(int(fired[0].task.id or 0), task_id)

        message = compose_message(fired[0], fire_at)
        self.assertIn("准时提醒", message.title)
        self.assertIn("截止", message.body)

        # 同一次运行内重复检查不会重复通知
        self.assertEqual(self.env.engine.claim_due(fire_at + timedelta(minutes=1)), [])

    def test_no_duplicate_after_restart(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        self.env.create_task(title="重启不重复", due_at=due)
        fire_at = due - timedelta(hours=24)
        self.assertEqual(len(self.env.engine.claim_due(fire_at)), 1)

        self.env.reopen()  # 模拟重启
        self.env.engine.rebuild_all()  # 启动时重建也不会丢失去重信息
        self.assertEqual(self.env.engine.claim_due(fire_at + timedelta(hours=1)), [])
        sent = self.env.db.scalar("SELECT COUNT(*) FROM reminders WHERE status = 'sent'")
        self.assertEqual(sent, 1)

    def test_missed_reminder_is_delivered_within_grace_window(self) -> None:
        due = rounded(NOW + timedelta(hours=13))  # 提醒时间 = 11 小时前，仍在 12 小时窗口内
        task_id = self.env.create_task(title="补发提醒", due_at=due)
        fired = self.env.engine.claim_due(NOW)
        self.assertEqual(len(fired), 1)
        self.assertGreater(fired[0].late, timedelta(hours=10))
        message = compose_message(fired[0], NOW)
        self.assertTrue(message.late_label)
        self.assertIn("补发", message.body)
        self.assertIn("补发", message.late_label)
        self.assertEqual(int(fired[0].task.id or 0), task_id)

    def test_missed_reminder_beyond_grace_is_skipped(self) -> None:
        due = rounded(NOW + timedelta(hours=1))  # 提醒时间 = 23 小时前
        self.env.create_task(title="太久以前", due_at=due)
        self.assertEqual(self.env.engine.claim_due(NOW), [])
        row = self.env.db.query_one(
            "SELECT status FROM reminders WHERE kind = 'due' ORDER BY id DESC LIMIT 1"
        )
        self.assertEqual(row["status"], "skipped")

    def test_completed_task_reminder_is_dropped(self) -> None:
        due = rounded(NOW + timedelta(hours=30))
        task_id = self.env.create_task(title="先完成", due_at=due)
        self.env.service.set_status(task_id, "done")
        self.assertEqual(self.env.engine.claim_due(due - timedelta(hours=24)), [])

    def test_snooze_delivers_again(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        self.env.create_task(title="稍后提醒", due_at=due, remind_due=True)
        fire_at = due - timedelta(hours=24)
        fired = self.env.engine.claim_due(fire_at)
        self.assertEqual(len(fired), 1)
        reminder_id = fired[0].reminder.id

        target = self.env.engine.snooze(int(reminder_id or 0), minutes=10, now=fire_at)
        self.assertEqual(target, fire_at + timedelta(minutes=10))
        self.assertEqual(self.env.engine.claim_due(fire_at + timedelta(minutes=5)), [])

        again = self.env.engine.claim_due(fire_at + timedelta(minutes=11))
        self.assertEqual(len(again), 1)
        self.assertEqual(again[0].reminder.snooze_count, 1)
        message = compose_message(again[0], fire_at + timedelta(minutes=11))
        self.assertIn("稍后提醒", message.body)

    def test_multiple_due_reminders_fire_in_order(self) -> None:
        base = rounded(NOW)
        first_due = base + timedelta(hours=26)   # 提醒时间 base+2h
        second_due = base + timedelta(hours=28)  # 提醒时间 base+4h
        self.env.create_task(title="先到期", due_at=first_due)
        self.env.create_task(title="后到期", due_at=second_due)
        fired = self.env.engine.claim_due(base + timedelta(hours=5))
        self.assertEqual(len(fired), 2)
        self.assertEqual([f.reminder.fire_at for f in fired], sorted(f.reminder.fire_at for f in fired))
        self.assertEqual(fired[0].task.title, "先到期")
        self.assertTrue(all(f.late > timedelta(0) for f in fired))

    def test_due_reminder_message_contains_remaining_time(self) -> None:
        due = rounded(NOW + timedelta(days=2))
        self.env.create_task(title="内容检查", due_at=due)
        fired = self.env.engine.claim_due(due - timedelta(hours=24))
        message = compose_message(fired[0], due - timedelta(hours=24))
        self.assertIn("还剩", message.body)
        self.assertIn("截止时间", message.body)


class OverdueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("overdue")

    def tearDown(self) -> None:
        self.env.close()

    def test_overdue_notice_only_once(self) -> None:
        past = rounded(NOW - timedelta(hours=3))
        task_id = self.env.create_task(title="逾期任务", due_at=past)
        fired = self.env.engine.check_overdue(NOW)
        self.assertEqual(len(fired), 1)
        self.assertTrue(fired[0].overdue_notice)
        message = compose_message(fired[0], NOW)
        self.assertIn("已逾期", message.title)
        self.assertIn("已逾期", message.body)

        self.assertEqual(self.env.engine.check_overdue(NOW + timedelta(minutes=10)), [])
        self.assertEqual(self.env.engine.check_overdue(NOW + timedelta(days=1)), [])

        # 逾期任务在列表里仍然明确标记
        task = self.env.service.get_task(task_id)
        self.assertTrue(task.is_overdue(NOW))
        self.assertTrue(task.overdue_notified)

    def test_overdue_suppresses_duplicate_due_reminder(self) -> None:
        past = rounded(NOW - timedelta(hours=3))
        self.env.create_task(title="逾期任务", due_at=past)
        self.assertEqual(len(self.env.engine.check_overdue(NOW)), 1)
        self.assertEqual(self.env.engine.claim_due(NOW), [])

    def test_reopened_task_overdue_not_notified_again(self) -> None:
        past = rounded(NOW - timedelta(hours=3))
        task_id = self.env.create_task(title="逾期再打开", due_at=past)
        self.env.engine.check_overdue(NOW)
        self.env.service.set_status(task_id, "done")
        self.env.service.set_status(task_id, "todo")
        self.assertEqual(self.env.engine.check_overdue(NOW), [])

    def test_due_change_resets_overdue_flag(self) -> None:
        past = rounded(NOW - timedelta(hours=3))
        task_id = self.env.create_task(title="改期后仍需提醒", due_at=past)
        self.env.engine.check_overdue(NOW)
        self.assertEqual(self.env.engine.check_overdue(NOW), [])

        task = self.env.service.get_task(task_id)
        draft = TaskDraft.from_task(task)
        draft.due_at = rounded(NOW - timedelta(hours=1))
        self.env.service.update_task(task_id, draft)
        self.assertEqual(len(self.env.engine.check_overdue(NOW)), 1)

    def test_snoozed_overdue_notice_can_fire_again(self) -> None:
        past = rounded(NOW - timedelta(hours=3))
        self.env.create_task(title="逾期稍后", due_at=past)
        fired = self.env.engine.check_overdue(NOW)
        reminder_id = int(fired[0].reminder.id or 0)
        self.env.engine.snooze(reminder_id, 10, now=NOW)
        self.assertEqual(self.env.engine.claim_due(NOW + timedelta(minutes=5)), [])
        again = self.env.engine.claim_due(NOW + timedelta(minutes=11))
        self.assertEqual(len(again), 1)
        self.assertEqual(again[0].kind, "overdue")


class SchedulerTest(unittest.TestCase):
    """后台调度器：与窗口无关，能处理睡眠恢复与系统时间跳变。"""

    @classmethod
    def setUpClass(cls) -> None:
        qapp()

    def setUp(self) -> None:
        self.env = TestEnv("scheduler")
        self.scheduler = ReminderScheduler(self.env.engine, self.env.settings, interval_seconds=20)
        self.reasons: list[str] = []
        self.scheduler.resynchronized.connect(self.reasons.append)

    def tearDown(self) -> None:
        self.scheduler.stop()
        self.env.close()

    def test_tick_fires_without_any_window(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        self.env.create_task(title="无窗口也能提醒", due_at=due)
        fire_at = due - timedelta(hours=24)
        messages = self.scheduler.tick(now=fire_at, monotonic=0.0)
        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], ReminderMessage)
        self.assertIn("无窗口也能提醒", messages[0].title)

    def test_tick_marks_sent_once(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        self.env.create_task(title="只响一次", due_at=due)
        fire_at = due - timedelta(hours=24)
        self.scheduler.tick(now=fire_at, monotonic=0.0)
        messages = self.scheduler.tick(now=fire_at + timedelta(seconds=20), monotonic=20.0)
        self.assertEqual(messages, [])

    def test_normal_ticks_do_not_resync(self) -> None:
        self.scheduler.tick(now=NOW, monotonic=100.0)
        self.scheduler.tick(now=NOW + timedelta(seconds=20), monotonic=120.0)
        self.assertEqual(self.reasons, [])

    def test_sleep_resume_triggers_resync_and_catch_up(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        self.env.create_task(title="睡眠后补查", due_at=due)
        fire_at = due - timedelta(hours=24)
        self.scheduler.tick(now=fire_at - timedelta(hours=1), monotonic=0.0)

        # 挂起 6 小时：程序计时器 6 小时没有跳动（挂起会被记到 elapsed 上）
        messages = self.scheduler.tick(now=fire_at + timedelta(hours=5), monotonic=6 * 3600.0)
        self.assertEqual(len(self.reasons), 1)
        self.assertIn("睡眠", self.reasons[0])
        self.assertEqual(len(messages), 1)
        self.assertIn("补发", messages[0].body)

    def test_clock_adjustment_triggers_resync(self) -> None:
        self.env.create_task(title="系统时间变化", due_at=NOW + timedelta(days=1))
        self.scheduler.tick(now=NOW, monotonic=0.0)
        self.scheduler.tick(now=NOW + timedelta(hours=3), monotonic=60.0)
        self.assertEqual(len(self.reasons), 1)
        self.assertIn("系统时间", self.reasons[0])

    def test_next_reminder_signal(self) -> None:
        due = rounded(NOW + timedelta(days=2))
        self.env.create_task(title="下一条", due_at=due)
        captured: list[object] = []
        self.scheduler.next_reminder_changed.connect(captured.append)
        self.scheduler.tick(now=NOW, monotonic=0.0)
        self.assertTrue(captured)
        info = captured[-1]
        self.assertIsInstance(info, dict)
        self.assertEqual(info["title"], "下一条")
        self.assertEqual(info["fire_at"], due - timedelta(hours=24))

    def test_scheduler_survives_database_error(self) -> None:
        due = rounded(NOW + timedelta(hours=2))
        self.env.create_task(title="写库失败", due_at=due)
        errors: list[str] = []
        self.scheduler.error_occurred.connect(errors.append)

        self.env.db.execute("PRAGMA query_only = ON")
        messages = self.scheduler.tick(now=due - timedelta(hours=24), monotonic=0.0)
        self.assertEqual(messages, [])
        self.assertTrue(errors, "数据库不可写时应通过信号上报错误")
        self.assertIn("数据库", errors[0])

        # 恢复可写后，下一次检查仍能正常补发（提醒没有被误标为已发送）
        self.env.db.execute("PRAGMA query_only = OFF")
        messages = self.scheduler.tick(now=due - timedelta(hours=24) + timedelta(seconds=20), monotonic=20.0)
        self.assertEqual(len(messages), 1)
        self.assertIn("写库失败", messages[0].title)


class FakeTray:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def showMessage(self, title, message, icon=None, msecs=0) -> None:  # noqa: N802
        self.messages.append((title, message))


class NotificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        qapp()

    def setUp(self) -> None:
        self.env = TestEnv("notify")
        self.env.settings.update(
            {"notification_sound": False, "inapp_notification": True, "system_notification": True}
        )

    def tearDown(self) -> None:
        self.env.close()

    def _manager(self, sender, tray=None, **kwargs):
        return NotificationManager(
            self.env.settings,
            toast_sender=sender,
            async_toast=False,
            tray_icon_provider=(lambda: tray) if tray is not None else None,
            **kwargs,
        )

    def _message(self) -> ReminderMessage:
        return ReminderMessage(
            title="截止提醒 · 测试任务",
            body="截止时间：10月25日 18:00\n还剩 1 天\n学习 · 重要",
            task_id=7,
            reminder_id=3,
            kind="due",
        )

    def test_toast_success_emits_popup_and_delivered(self) -> None:
        calls: list[ReminderMessage] = []
        manager = self._manager(lambda m: (calls.append(m), (True, "ok"))[1])
        popups: list[object] = []
        delivered: list[tuple] = []
        manager.popup_requested.connect(popups.append)
        manager.delivered.connect(lambda m, ch: delivered.append((m, ch)))

        channel = manager.notify(self._message())
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(popups), 1)
        self.assertIn("toast", channel)
        self.assertIn("inapp", channel)
        self.assertEqual(delivered[0][1], channel)

    def test_toast_failure_falls_back_to_tray(self) -> None:
        tray = FakeTray()
        manager = self._manager(lambda m: (False, "系统拒绝"), tray=tray)
        failures: list[str] = []
        manager.failed.connect(failures.append)

        manager.notify(self._message())
        self.assertEqual(len(tray.messages), 1)
        self.assertIn("测试任务", tray.messages[0][0])
        self.assertTrue(failures)

    def test_inapp_disabled_but_system_still_works(self) -> None:
        self.env.settings.set("inapp_notification", False)
        popups: list[object] = []
        manager = self._manager(lambda m: (True, "ok"))
        manager.popup_requested.connect(popups.append)
        channel = manager.notify(self._message())
        self.assertEqual(popups, [])
        self.assertIn("toast", channel)

    def test_system_disabled_uses_tray(self) -> None:
        self.env.settings.set("system_notification", False)
        tray = FakeTray()
        manager = self._manager(lambda m: (True, "ok"), tray=tray)
        channel = manager.notify(self._message())
        self.assertIn("tray", channel)
        self.assertEqual(len(tray.messages), 1)

    def test_toast_xml_has_actions_and_protocol(self) -> None:
        xml = build_toast_xml(self._message())
        self.assertIn("weeklyplanner://task/7", xml)
        self.assertIn("weeklyplanner://snooze/3", xml)
        self.assertIn("查看任务", xml)
        self.assertIn("稍后提醒", xml)
        self.assertIn("截止提醒 · 测试任务", xml)
        self.assertIn("Notification.Reminder", xml)

    def test_toast_script_mentions_aumid_and_escapes(self) -> None:
        script = build_toast_script(build_toast_xml(self._message()))
        self.assertIn("Windows.UI.Notifications", script)
        self.assertIn("WeeklyPlanner.Desktop", script)
        self.assertIn("LoadXml", script)
        # 未打包程序需要显式设置进程 AppUserModelID 作为兜底
        self.assertIn("SetCurrentProcessExplicitAppUserModelID", script)
        self.assertIn("CreateToastNotifier()", script)

    def test_xml_escapes_html(self) -> None:
        message = ReminderMessage(
            title="<b>危险</b> & 特殊字符",
            body="内容",
            task_id=1,
            reminder_id=1,
            kind="due",
        )
        xml = build_toast_xml(message)
        self.assertNotIn("<b>危险</b>", xml)
        self.assertIn("&lt;b&gt;", xml)
        self.assertIn("&amp;", xml)

    def test_compose_message_for_plan(self) -> None:
        due = rounded(NOW + timedelta(days=2))
        task_id = self.env.create_task(
            title="计划提醒测试",
            due_at=due,
            plans=[PlanDraft(plan_at=rounded(NOW + timedelta(hours=2)), label="写初稿", remind_enabled=True)],
        )
        task = self.env.service.get_task(task_id)
        fired = self.env.engine.claim_due(rounded(NOW + timedelta(hours=1, minutes=50)))
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].kind, "plan")
        message = compose_message(fired[0], rounded(NOW + timedelta(hours=1, minutes=50)))
        self.assertIn("计划提醒", message.title)
        self.assertIn("写初稿", message.body)
        self.assertIn("还剩", message.body)
        self.assertEqual(message.task_id, task_id)
        _ = task


if __name__ == "__main__":
    unittest.main()
