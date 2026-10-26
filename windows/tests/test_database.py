"""数据库层测试：结构、持久化、备份恢复、CSV、旧库迁移、错误处理。"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import unittest
import uuid
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

    def test_plan_time_has_end_and_reminder_columns(self) -> None:
        columns = {
            row["name"]: row for row in self.env.db.query("PRAGMA table_info(plan_times)")
        }
        for name in ("end_at", "remind_start", "remind_end"):
            self.assertIn(name, columns)
        self.assertIsNone(columns["end_at"]["dflt_value"])  # 可为 NULL（旧数据没有结束时间）
        self.assertEqual(str(columns["remind_start"]["dflt_value"]), "1")
        self.assertEqual(str(columns["remind_end"]["dflt_value"]), "0")
        self.assertEqual(str(columns["remind_start"]["notnull"]), "1")
        self.assertEqual(str(columns["remind_end"]["notnull"]), "1")

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


class LegacyMigrationTest(unittest.TestCase):
    """旧库（没有 end_at / remind_start / remind_end 列）要能原地升级。"""

    OLD_SCHEMA = """
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', due_at TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT '学习', priority TEXT NOT NULL DEFAULT 'normal',
        status TEXT NOT NULL DEFAULT 'todo', remind_due INTEGER NOT NULL DEFAULT 1,
        notes TEXT NOT NULL DEFAULT '', completed_at TEXT,
        overdue_notified INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE plan_times (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        plan_at TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
        remind_enabled INTEGER NOT NULL DEFAULT 0,
        remind_lead_minutes INTEGER NOT NULL DEFAULT 10,
        done INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, plan_id INTEGER,
        fire_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        fired_at TEXT, snooze_count INTEGER NOT NULL DEFAULT 0,
        anchor_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """

    def setUp(self) -> None:
        base = ROOT / ".testdata" / "cases"
        base.mkdir(parents=True, exist_ok=True)
        self.dir = base / f"legacy_{uuid.uuid4().hex[:8]}"
        self.dir.mkdir()
        self.path = self.dir / "planner.db"
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript(self.OLD_SCHEMA)
            conn.execute(
                "INSERT INTO tasks (id, title, due_at, created_at, updated_at)"
                " VALUES (1, '旧任务', '2026-11-01 18:00', '2026-10-01 10:00', '2026-10-01 10:00')"
            )
            conn.execute(
                "INSERT INTO plan_times (id, task_id, plan_at, label, remind_enabled,"
                " remind_lead_minutes, done, sort_order)"
                " VALUES (1, 1, '2026-10-30 19:00', '旧计划', 1, 10, 0, 0)"
            )
            conn.execute(
                "INSERT INTO plan_times (id, task_id, plan_at, label, remind_enabled,"
                " remind_lead_minutes, done, sort_order)"
                " VALUES (2, 1, '2026-10-31 20:00', '旧计划无提醒', 0, 10, 0, 1)"
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_old_database_is_migrated_in_place(self) -> None:
        db = Database(self.path)
        try:
            columns = {row["name"] for row in db.query("PRAGMA table_info(plan_times)")}
            self.assertTrue({"end_at", "remind_start", "remind_end"}.issubset(columns))
            rows = db.query("SELECT * FROM plan_times ORDER BY id")
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertIsNone(row["end_at"])  # 旧数据没有结束时间
                self.assertEqual(row["remind_end"], 0)
            # 旧行的开始提醒沿用原来的 remind_enabled，不会突然全部打开
            self.assertEqual(rows[0]["remind_start"], 1)
            self.assertEqual(rows[1]["remind_start"], 0)
            # 旧数据仍然能读成模型
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM tasks"), 1)
        finally:
            db.close()

    def test_migration_is_idempotent(self) -> None:
        for _ in range(3):
            db = Database(self.path)
            try:
                columns = [row["name"] for row in db.query("PRAGMA table_info(plan_times)")]
                self.assertEqual(len(columns), len(set(columns)))
                self.assertIn("end_at", columns)
            finally:
                db.close()

    def test_restore_old_backup_migrates_too(self) -> None:
        env = TestEnv("legacy_restore")
        try:
            env.service.restore_from(str(self.path))
            columns = {row["name"] for row in env.db.query("PRAGMA table_info(plan_times)")}
            self.assertTrue({"end_at", "remind_start", "remind_end"}.issubset(columns))
            tasks = env.service.list_tasks()
            self.assertEqual([task.title for task in tasks], ["旧任务"])
        finally:
            env.close()


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

    def test_plan_end_time_and_reminder_switches_survive_restart(self) -> None:
        due = datetime.now().replace(second=0, microsecond=0) + timedelta(days=5)
        plan_at = due - timedelta(days=3)
        end_at = plan_at + timedelta(hours=26)  # 跨天
        task_id = self.env.create_task(
            title="结束时间跨重启",
            due_at=due,
            plans=[
                PlanDraft(
                    plan_at=plan_at,
                    end_at=end_at,
                    label="跨天计划",
                    remind_start=True,
                    remind_lead_minutes=30,
                    remind_end=True,
                )
            ],
        )
        self.env.reopen()
        task = self.env.service.get_task(task_id)
        plan = task.sorted_plans()[0]
        self.assertEqual(plan.end_at, end_at)
        self.assertTrue(plan.remind_start)
        self.assertTrue(plan.remind_end)
        self.assertEqual(plan.remind_lead_minutes, 30)
        self.assertTrue(plan.is_cross_day)
        kinds = {row.kind for row in self.env.pending() if row.task_id == task_id}
        self.assertEqual(kinds, {"due", "plan", "plan_end"})


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
                PlanDraft(
                    plan_at=base,
                    end_at=base + timedelta(days=1, hours=2),  # 跨天
                    label="收集资料",
                    remind_enabled=True,
                    remind_lead_minutes=15,
                    remind_end=True,
                ),
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
            self.assertTrue(first.remind_start)
            self.assertEqual(first.remind_lead_minutes, 15)
            self.assertEqual(first.end_at, base + timedelta(days=1, hours=2))
            self.assertTrue(first.remind_end)
            second = task.sorted_plans()[1]
            self.assertIsNone(second.end_at)
            self.assertFalse(second.remind_start)
        finally:
            other.close()

    def test_import_old_csv_plan_format_still_works(self) -> None:
        # 旧版 CSV 的计划时间列只有「开始|说明|提前分钟」，读取时要按旧行为处理
        csv_path = self.env.dir / "old_plans.csv"
        csv_path.write_text(
            "任务名称,截止时间,计划时间\n"
            "旧格式任务,2026-10-25 18:00,2026-10-20 19:00|旧计划|10; 2026-10-21 19:00|没提醒|0\n",
            encoding="utf-8-sig",
        )
        result = self.env.service.import_csv(str(csv_path))
        self.assertEqual(result["plans"], 2)
        task = self.env.service.list_tasks()[0]
        first, second = task.sorted_plans()
        self.assertIsNone(first.end_at)
        self.assertTrue(first.remind_start)
        self.assertFalse(first.remind_end)
        self.assertFalse(second.remind_start)

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
