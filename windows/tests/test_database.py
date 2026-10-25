"""数据库层测试：结构、持久化、备份恢复、CSV、错误处理。"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support import TestEnv  # noqa: E402

from src.database import Database, DatabaseError  # noqa: E402
from src.models import PlanDraft, TaskDraft  # noqa: E402


class DatabaseSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("schema")

    def tearDown(self) -> None:
        self.env.close()

    def test_tables_and_indexes_created(self) -> None:
        names = {
            row[0]
            for row in self.env.db.query(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for expected in ("tasks", "plan_times", "reminders", "settings"):
            self.assertIn(expected, names)

        version = self.env.db.scalar("PRAGMA user_version")
        self.assertEqual(version, 2)

        # 唯一索引保证同一任务同一时刻只有一条提醒，避免重复通知
        indexes = {
            row[0]
            for row in self.env.db.query(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        self.assertIn("idx_reminders_identity", indexes)

    def test_settings_defaults_and_persistence(self) -> None:
        self.assertEqual(self.env.settings.get_str("theme"), "light")
        self.assertEqual(self.env.settings.get_str("reminder_mode"), "before_due_24h")
        self.assertEqual(self.env.settings.get_int("missed_grace_hours"), 12)
        self.assertEqual(self.env.settings.categories, ["学习", "工作", "生活"])

        self.env.settings.set("theme", "dark")
        self.env.settings.set("previous_day_time", "08:30")
        self.env.settings.add_category("健身")

        self.env.reopen()
        self.assertEqual(self.env.settings.get_str("theme"), "dark")
        self.assertEqual(self.env.settings.get_str("previous_day_time"), "08:30")
        self.assertIn("健身", self.env.settings.categories)
        policy = self.env.settings.reminder_policy()
        self.assertEqual(policy.previous_day_time, "08:30")

    def test_foreign_keys_cascade_on_delete(self) -> None:
        task_id = self.env.create_task(
            title="级联删除",
            plans=[PlanDraft(plan_at=datetime.now() + timedelta(days=1))],
        )
        self.assertGreater(len(self.env.reminder_rows(task_id)), 0)
        self.env.service.delete_task(task_id)
        self.assertEqual(self.env.db.scalar("SELECT COUNT(*) FROM plan_times"), 0)
        self.assertEqual(self.env.db.scalar("SELECT COUNT(*) FROM reminders"), 0)


class PersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("persist")

    def tearDown(self) -> None:
        self.env.close()

    def test_all_data_survives_restart(self) -> None:
        due = datetime.now().replace(second=0, microsecond=0) + timedelta(days=3)
        task_id = self.env.create_task(
            title="跨重启保留",
            description="说明文字",
            due_at=due,
            category="学习",
            priority="important",
            status="doing",
            remind_due=True,
            notes="备注内容",
            plans=[
                PlanDraft(plan_at=due - timedelta(days=2), label="第一步", remind_enabled=True, remind_lead_minutes=30),
                PlanDraft(plan_at=due - timedelta(days=1), label="第二步"),
            ],
        )
        self.env.settings.set("theme", "dark")
        pending_before = len(self.env.pending())
        self.assertEqual(pending_before, 2)  # 截止提醒 + 第一个计划提醒

        self.env.reopen()

        task = self.env.service.get_task(task_id)
        self.assertEqual(task.title, "跨重启保留")
        self.assertEqual(task.description, "说明文字")
        self.assertEqual(task.notes, "备注内容")
        self.assertEqual(task.category, "学习")
        self.assertEqual(task.priority, "important")
        self.assertEqual(task.status, "doing")
        self.assertTrue(task.remind_due)
        self.assertEqual(len(task.plans), 2)
        self.assertEqual(task.sorted_plans()[0].label, "第一步")
        self.assertTrue(task.sorted_plans()[0].remind_enabled)
        self.assertEqual(len(self.env.pending()), pending_before)
        self.assertEqual(self.env.settings.get_str("theme"), "dark")


class BackupRestoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("backup")

    def tearDown(self) -> None:
        self.env.close()

    def test_backup_then_restore(self) -> None:
        self.env.create_task(title="备份前任务")
        backup_path = self.env.dir / "backup.db"
        self.env.service.backup_to(str(backup_path))
        self.assertTrue(backup_path.exists())
        ok, reason = Database.validate_backup(backup_path)
        self.assertTrue(ok, reason)

        self.env.create_task(title="备份后新增")
        self.assertEqual(self.env.task_count(), 2)

        self.env.service.restore_from(str(backup_path))
        titles = [task.title for task in self.env.service.list_tasks()]
        self.assertEqual(titles, ["备份前任务"])

    def test_restore_rejects_invalid_file(self) -> None:
        bad = self.env.dir / "bad.db"
        bad.write_text("这不是数据库", encoding="utf-8")
        with self.assertRaises(DatabaseError) as ctx:
            self.env.service.restore_from(str(bad))
        self.assertIn("无法恢复", str(ctx.exception))
        self.assertTrue((self.env.dir / "missing.db").exists() is False)

    def test_restore_keeps_old_file_copy(self) -> None:
        self.env.create_task(title="原数据")
        backup_path = self.env.dir / "backup2.db"
        self.env.service.backup_to(str(backup_path))
        self.env.service.restore_from(str(backup_path))
        self.assertTrue((self.env.db_path.with_suffix(".before-restore.db")).exists())


class CsvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("csv")

    def tearDown(self) -> None:
        self.env.close()

    def test_export_import_roundtrip(self) -> None:
        base = datetime(2026, 10, 20, 19, 0)
        self.env.create_task(
            title="CSV 任务一",
            description="第一行\n第二行",
            due_at=base + timedelta(days=5),
            category="工作",
            priority="urgent",
            status="doing",
            notes="带,逗号",
            plans=[
                PlanDraft(plan_at=base, label="收集资料", remind_enabled=True, remind_lead_minutes=15),
                PlanDraft(plan_at=base + timedelta(days=2), label="初稿", remind_enabled=False),
            ],
        )
        self.env.create_task(title="CSV 任务二", due_at=base + timedelta(days=1), category="生活")
        csv_path = self.env.dir / "out.csv"
        exported = self.env.service.export_csv(str(csv_path))
        self.assertEqual(exported, 2)

        other = TestEnv("csv_import")
        try:
            result = other.service.import_csv(str(csv_path))
            self.assertEqual(result["tasks"], 2)
            self.assertEqual(result["plans"], 2)
            self.assertEqual(result["skipped"], 0)

            tasks = {task.title: task for task in other.service.list_tasks()}
            self.assertIn("CSV 任务一", tasks)
            task = tasks["CSV 任务一"]
            self.assertEqual(task.category, "工作")
            self.assertEqual(task.priority, "urgent")
            self.assertEqual(task.status, "doing")
            self.assertIn("带,逗号", task.notes)
            self.assertEqual(len(task.plans), 2)
            first = task.sorted_plans()[0]
            self.assertEqual(first.label, "收集资料")
            self.assertTrue(first.remind_enabled)
            self.assertEqual(first.remind_lead_minutes, 15)
        finally:
            other.close()

    def test_import_skips_invalid_rows(self) -> None:
        csv_path = self.env.dir / "partial.csv"
        csv_path.write_text(
            "任务名称,截止时间\n"
            "有效任务,2026-10-25 18:00\n"
            ",2026-10-25 18:00\n"
            "时间无效,不是时间\n",
            encoding="utf-8-sig",
        )
        result = self.env.service.import_csv(str(csv_path))
        self.assertEqual(result["tasks"], 1)
        self.assertEqual(result["skipped"], 2)

    def test_import_requires_columns(self) -> None:
        csv_path = self.env.dir / "bad.csv"
        csv_path.write_text("名称\nfoo\n", encoding="utf-8-sig")
        with self.assertRaises(DatabaseError):
            self.env.service.import_csv(str(csv_path))


class WriteFailureTest(unittest.TestCase):
    """数据库不可写时必须抛出带中文说明的 DatabaseError。"""

    def setUp(self) -> None:
        self.env = TestEnv("failure")

    def tearDown(self) -> None:
        self.env.close()

    def test_write_failure_raises_database_error(self) -> None:
        self.env.db.execute("PRAGMA query_only = ON")
        with self.assertRaises(DatabaseError) as ctx:
            self.env.db.insert(
                "INSERT INTO settings(key, value) VALUES (?, ?)", ("k", "v")
            )
        error = ctx.exception
        self.assertIn("数据库写入失败", str(error))
        self.assertTrue(error.user_message())
        self.assertTrue(error.detail)

    def test_service_write_failure_is_reported(self) -> None:
        self.env.db.execute("PRAGMA query_only = ON")
        with self.assertRaises(DatabaseError) as ctx:
            self.env.service.create_task(TaskDraft(title="写不进去", due_at=datetime.now()))
        self.assertIn("保存", ctx.exception.user_message() + "保存")

    def test_cannot_create_database_in_file_path(self) -> None:
        blocker = self.env.dir / "blocker.txt"
        blocker.write_text("x", encoding="utf-8")
        with self.assertRaises(DatabaseError) as ctx:
            Database(blocker / "nested" / "planner.db")
        self.assertIn("数据目录", ctx.exception.user_message() + str(ctx.exception))

    def test_unreadable_database_file_raises(self) -> None:
        bad = self.env.dir / "corrupt.db"
        bad.write_bytes(b"not a sqlite database at all" * 40)
        with self.assertRaises(DatabaseError) as ctx:
            Database(bad)
        self.assertIn("数据库", ctx.exception.user_message() + str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
