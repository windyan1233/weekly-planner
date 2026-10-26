"""Windows ↔ Android JSON 互通测试。"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

import unittest

from tests.support import ROOT

from src.database import Database
from src.exchange import FORMAT, export_payload, import_payload
from src.finance.finance_database import FinanceDatabase


class ExchangeTest(unittest.TestCase):
    def setUp(self) -> None:
        base = ROOT / ".testdata" / "cases"
        base.mkdir(parents=True, exist_ok=True)
        self.dir = base / f"exchange_{uuid.uuid4().hex[:8]}"
        self.dir.mkdir()
        self.planner = Database(self.dir / "planner.db")
        self.finance = FinanceDatabase(self.dir / "finance.db", schedule_db_path=self.dir / "planner.db")

    def tearDown(self) -> None:
        try:
            self.planner.close()
        except Exception:
            pass
        try:
            self.finance.close()
        except Exception:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def _seed(self) -> None:
        now = datetime(2026, 10, 19, 20, 0).strftime("%Y-%m-%d %H:%M")
        self.planner.execute(
            "INSERT INTO tasks (id, title, description, due_at, category, priority, status, "
            "remind_due, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (1, "写作业", "", "2026-10-22 18:00", "学习", "important", "todo", 1, "备注", now, now),
        )
        self.planner.execute(
            "INSERT INTO plan_times (id, task_id, plan_at, label, remind_enabled, "
            "remind_lead_minutes, done, sort_order) VALUES (?,?,?,?,?,?,?,?)",
            (1, 1, "2026-10-20 09:00", "上午", 0, 10, 0, 0),
        )
        self.planner.execute(
            "INSERT INTO courses (id, name, teacher, location, descriptor, color, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (1, "高等数学I", "张三", "图一", "高数", "#6C8AE4", now),
        )
        self.planner.execute(
            "INSERT INTO course_sessions (id, course_id, day, start_minutes, end_minutes, skipped) "
            "VALUES (?,?,?,?,?,?)",
            (1, 1, "2026-10-20", 510, 605, 0),
        )
        self.finance.execute(
            "INSERT INTO accounts (id, name, note, opening_cents, created_at, archived, system) "
            "VALUES (?,?,?,?,?,?,?)",
            (1, "现金", "", 10000, now, 0, 0),
        )
        self.finance.execute(
            "INSERT INTO accounts (id, name, note, opening_cents, created_at, archived, system) "
            "VALUES (?,?,?,?,?,?,?)",
            (2, "饭卡", "", 5000, now, 0, 0),
        )
        self.finance.execute(
            "INSERT INTO transactions (id, kind, amount_cents, occurred_on, title, category, "
            "account_id, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (1, "expense", 2000, "2026-10-18", "午饭", "food", 1, "", now, now),
        )
        self.finance.execute(
            "INSERT INTO transfers (id, from_account_id, to_account_id, amount_cents, "
            "occurred_on, note, created_at) VALUES (?,?,?,?,?,?,?)",
            (1, 1, 2, 100, "2026-10-19", "", now),
        )

    def test_export_shape(self) -> None:
        self._seed()
        payload = export_payload(self.planner, self.finance)
        self.assertEqual(payload["format"], FORMAT)
        self.assertEqual(payload["source"], "windows")
        self.assertEqual(len(payload["tasks"]), 1)
        self.assertEqual(len(payload["courses"]), 1)
        self.assertEqual(payload["courses"][0]["name"], "高等数学I")
        task = payload["tasks"][0]
        self.assertIsInstance(task["dueAt"], int)
        self.assertEqual(task["priority"], "important")
        self.assertTrue(task["dueAt"] > 0)
        self.assertIn("remindDue", task)
        self.assertEqual(
            {"id", "taskId", "planAt", "endAt", "remindStart", "remindEnd"},
            set(payload["plans"][0]),
        )
        self.assertEqual(payload["transactions"][0]["type"], "expense")
        self.assertEqual(payload["transactions"][0]["categoryKey"], "food")
        json.dumps(payload, ensure_ascii=False)

    def test_plan_end_and_reminder_switches_roundtrip(self) -> None:
        self._seed()
        end_at = datetime(2026, 10, 21, 11, 0)
        self.planner.execute(
            "UPDATE plan_times SET end_at = ?, remind_start = 0, remind_end = 1 WHERE id = 1",
            ("2026-10-21 11:00",),
        )
        self.planner.execute("UPDATE tasks SET remind_due = 0 WHERE id = 1")
        payload = export_payload(self.planner, self.finance)

        self.assertFalse(payload["tasks"][0]["remindDue"])
        plan = payload["plans"][0]
        self.assertEqual(plan["endAt"], int(end_at.timestamp() * 1000))
        self.assertFalse(plan["remindStart"])
        self.assertTrue(plan["remindEnd"])

        other_dir = self.dir / "other_fields"
        other_dir.mkdir()
        planner2 = Database(other_dir / "planner.db")
        finance2 = FinanceDatabase(other_dir / "finance.db", schedule_db_path=other_dir / "planner.db")
        try:
            import_payload(planner2, finance2, payload)
            row = planner2.query_one("SELECT * FROM plan_times WHERE id = 1")
            self.assertIsNotNone(row)
            self.assertEqual(row["end_at"], "2026-10-21 11:00")
            self.assertEqual(row["remind_start"], 0)
            self.assertEqual(row["remind_end"], 1)
            self.assertEqual(row["remind_enabled"], 0)  # 旧字段与 remind_start 同步
            task_row = planner2.query_one("SELECT * FROM tasks WHERE id = 1")
            self.assertEqual(task_row["remind_due"], 0)
        finally:
            planner2.close()
            finance2.close()

    def test_old_json_without_new_plan_fields_uses_defaults(self) -> None:
        plan_at = datetime(2026, 10, 20, 9, 0)
        payload = {
            "format": FORMAT,
            "version": 1,
            "source": "android",
            "tasks": [{"id": 5, "title": "旧 JSON 任务", "dueAt": int(plan_at.timestamp() * 1000)}],
            "plans": [
                {"id": 9, "taskId": 5, "planAt": int(plan_at.timestamp() * 1000)},
            ],
            "courses": [],
            "courseSessions": [],
            "accounts": [],
            "transactions": [],
            "transfers": [],
            "reports": [],
        }
        import_payload(self.planner, self.finance, payload)
        plan = self.planner.query_one("SELECT * FROM plan_times WHERE id = 9")
        self.assertIsNotNone(plan)
        self.assertIsNone(plan["end_at"])
        self.assertEqual(plan["remind_start"], 1)  # 数据库默认值
        self.assertEqual(plan["remind_end"], 0)
        task = self.planner.query_one("SELECT * FROM tasks WHERE id = 5")
        self.assertEqual(task["remind_due"], 1)

    def test_roundtrip(self) -> None:
        self._seed()
        payload = export_payload(self.planner, self.finance)

        other_dir = self.dir / "other"
        other_dir.mkdir()
        planner2 = Database(other_dir / "planner.db")
        finance2 = FinanceDatabase(other_dir / "finance.db", schedule_db_path=other_dir / "planner.db")
        try:
            counts = import_payload(planner2, finance2, payload)
            self.assertEqual(counts["tasks"], 1)
            self.assertEqual(counts["courses"], 1)
            task = planner2.query_one("SELECT * FROM tasks WHERE id = 1")
            self.assertIsNotNone(task)
            self.assertEqual(task["title"], "写作业")
            self.assertEqual(task["priority"], "important")
            self.assertEqual(task["notes"], "备注")
            plan = planner2.query_one("SELECT * FROM plan_times WHERE task_id = 1")
            self.assertIsNotNone(plan)
            course = planner2.query_one("SELECT * FROM courses WHERE id = 1")
            self.assertIsNotNone(course)
            info = planner2.query_one("SELECT * FROM course_sessions WHERE course_id = 1")
            self.assertIsNotNone(info)
            self.assertEqual(info["start_minutes"], 510)
            account = finance2.query_one("SELECT * FROM accounts WHERE id = 1")
            self.assertIsNotNone(account)
            self.assertEqual(account["opening_cents"], 10000)
            tx = finance2.query_one("SELECT * FROM transactions WHERE id = 1")
            self.assertEqual(tx["category"], "food")
            self.assertEqual(tx["occurred_on"], "2026-10-18")
        finally:
            planner2.close()
            finance2.close()

    def test_android_payload_without_due_date(self) -> None:
        payload = {
            "format": FORMAT,
            "version": 1,
            "source": "android",
            "tasks": [
                {
                    "id": 5,
                    "title": "没截止时间的任务",
                    "note": "",
                    "kind": "学习",
                    "priority": "urgent",
                    "dueAt": None,
                    "done": False,
                    "createdAt": 1_700_000_000_000,
                    "updatedAt": 1_700_000_000_000,
                }
            ],
            "plans": [],
            "accounts": [],
            "transactions": [],
            "transfers": [],
            "reports": [],
            "courses": [],
            "courseSessions": [],
        }
        counts = import_payload(self.planner, self.finance, payload)
        self.assertEqual(counts["tasks"], 1)
        task = self.planner.query_one("SELECT * FROM tasks WHERE id = 5")
        self.assertIsNotNone(task)
        self.assertTrue(task["due_at"])
        self.assertEqual(task["priority"], "urgent")

    def test_rejects_unknown_format(self) -> None:
        with self.assertRaises(ValueError):
            import_payload(self.planner, self.finance, {"format": "something-else"})


if __name__ == "__main__":
    unittest.main()
