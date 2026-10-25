"""任务服务层测试：多计划时间、编辑、完成、搜索、筛选、复制、逾期。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support import TestEnv, at, week_start_of  # noqa: E402

from src.models import PlanDraft, TaskDraft  # noqa: E402
from src.task_manager import TaskFilter, ValidationError  # noqa: E402


class CreateTaskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("create")

    def tearDown(self) -> None:
        self.env.close()

    def test_create_with_due_and_multiple_plans(self) -> None:
        base = datetime(2026, 10, 20, 19, 0)
        task_id = self.env.create_task(
            title="完成课程报告",
            description="写 12 页",
            due_at=datetime(2026, 10, 25, 18, 0),
            category="学习",
            priority="important",
            plans=[
                PlanDraft(plan_at=base, label="收集资料"),
                PlanDraft(plan_at=base + timedelta(days=2, hours=1), label="完成初稿"),
                PlanDraft(plan_at=base + timedelta(days=4), label="检查并修改"),
            ],
        )
        task = self.env.service.get_task(task_id)
        self.assertEqual(task.title, "完成课程报告")
        self.assertEqual(task.due_at, datetime(2026, 10, 25, 18, 0))
        self.assertEqual(len(task.plans), 3)
        labels = [plan.label for plan in task.sorted_plans()]
        self.assertEqual(labels, ["收集资料", "完成初稿", "检查并修改"])
        # 计划时间与截止时间完全独立
        self.assertNotEqual(task.plans[0].plan_at, task.due_at)
        self.assertEqual(task.due_at, datetime(2026, 10, 25, 18, 0))

    def test_title_is_required(self) -> None:
        with self.assertRaises(ValidationError):
            self.env.service.create_task(TaskDraft(title="   ", due_at=datetime.now()))
        self.assertEqual(self.env.task_count(), 0)

    def test_invalid_priority_falls_back_to_normal(self) -> None:
        task_id = self.env.create_task(title="优先级", priority="whatever")
        self.assertEqual(self.env.service.get_task(task_id).priority, "normal")

    def test_same_day_multiple_plans_are_kept_separately(self) -> None:
        day = datetime(2026, 10, 21, 9, 0)
        task_id = self.env.create_task(
            title="同一天多个计划",
            due_at=day + timedelta(hours=12),
            plans=[
                PlanDraft(plan_at=day, label="上午"),
                PlanDraft(plan_at=day + timedelta(hours=2), label="中午"),
            ],
        )
        task = self.env.service.get_task(task_id)
        self.assertEqual(len(task.plans), 2)
        self.assertNotEqual(task.plans[0].id, task.plans[1].id)


class PlanTimeEditingTest(unittest.TestCase):
    """单独修改 / 删除某个计划时间，不影响其它计划时间和任务本身。"""

    def setUp(self) -> None:
        self.env = TestEnv("plans")
        base = datetime(2026, 10, 20, 19, 0)
        self.base = base
        self.task_id = self.env.create_task(
            title="多计划任务",
            due_at=datetime(2026, 10, 25, 18, 0),
            plans=[
                PlanDraft(plan_at=base, label="A"),
                PlanDraft(plan_at=base + timedelta(days=2), label="B"),
                PlanDraft(plan_at=base + timedelta(days=4), label="C"),
            ],
        )
        self.plans = self.env.service.get_task(self.task_id).sorted_plans()

    def tearDown(self) -> None:
        self.env.close()

    def test_update_one_plan_keeps_others(self) -> None:
        target = self.plans[1]
        self.env.service.update_plan(
            int(target.id or 0), plan_at=self.base + timedelta(days=3), label="B 改期"
        )
        task = self.env.service.get_task(self.task_id)
        self.assertEqual(len(task.plans), 3)
        self.assertEqual(task.plans[0].label, "A")
        self.assertEqual(task.plans[1].label, "B 改期")
        self.assertEqual(task.plans[1].plan_at, self.base + timedelta(days=3))
        self.assertEqual(task.plans[2].label, "C")
        self.assertEqual(task.due_at, datetime(2026, 10, 25, 18, 0))

    def test_delete_one_plan_keeps_task_and_others(self) -> None:
        target = self.plans[0]
        self.env.service.delete_plan(int(target.id or 0))
        task = self.env.service.get_task(self.task_id)
        self.assertEqual(len(task.plans), 2)
        self.assertEqual([p.label for p in task.sorted_plans()], ["B", "C"])
        self.assertEqual(self.env.task_count(), 1)

    def test_toggle_plan_done_removes_only_its_reminder(self) -> None:
        plan = self.env.service.update_plan(
            int(self.plans[0].id or 0), remind_enabled=True, remind_lead_minutes=10
        )
        self.assertTrue(plan.remind_enabled)
        pending = {row.kind for row in self.env.pending()}
        self.assertIn("plan", pending)

        self.env.service.set_plan_done(int(plan.id or 0), True)
        plan_reminders = [row for row in self.env.pending() if row.plan_id == plan.id]
        self.assertEqual(plan_reminders, [])
        # 截止提醒仍然存在
        self.assertTrue(any(row.kind == "due" for row in self.env.pending()))

    def test_add_plan_to_existing_task(self) -> None:
        new_plan = self.env.service.add_plan(
            self.task_id, self.base + timedelta(days=5), label="D", remind_enabled=True
        )
        task = self.env.service.get_task(self.task_id)
        self.assertEqual(len(task.plans), 4)
        self.assertTrue(new_plan.remind_enabled)
        self.assertTrue(any(row.plan_id == new_plan.id for row in self.env.pending()))

    def test_update_task_reconciles_plan_ids(self) -> None:
        draft = TaskDraft.from_task(self.env.service.get_task(self.task_id))
        kept = draft.plans[0]
        removed = draft.plans[1]
        removed_id = removed.id
        draft.plans = [kept, PlanDraft(plan_at=self.base + timedelta(days=1), label="新的计划")]
        draft.title = "改过名字"
        self.env.service.update_task(self.task_id, draft)
        task = self.env.service.get_task(self.task_id)
        self.assertEqual(task.title, "改过名字")
        self.assertEqual(len(task.plans), 2)
        self.assertIsNone(self.env.db.query_one("SELECT id FROM plan_times WHERE id = ?", (removed_id,)))
        self.assertIsNotNone(self.env.db.query_one("SELECT id FROM plan_times WHERE id = ?", (kept.id,)))

    def test_update_missing_task_raises(self) -> None:
        from src.task_manager import TaskNotFoundError

        with self.assertRaises(TaskNotFoundError):
            self.env.service.update_task(9999, TaskDraft(title="x", due_at=datetime.now()))


class StatusAndWeeklyViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("week")
        self.due = datetime(2026, 10, 25, 18, 0)  # 周日
        self.task_id = self.env.create_task(
            title="周视图任务",
            due_at=self.due,
            category="学习",
            priority="important",
            plans=[
                PlanDraft(plan_at=datetime(2026, 10, 20, 19, 0), label="收集资料"),
                PlanDraft(plan_at=datetime(2026, 10, 22, 20, 0), label="初稿"),
                PlanDraft(plan_at=datetime(2026, 10, 24, 15, 0), label="修改"),
            ],
        )

    def tearDown(self) -> None:
        self.env.close()

    def test_occurrences_cover_each_plan_day_and_due(self) -> None:
        week_start = week_start_of(self.due.date())
        occurrences = self.env.service.occurrences(week_start)
        self.assertEqual(len(occurrences), 4)
        plan_occurrences = [occ for occ in occurrences if occ.kind == "plan"]
        due_occurrences = [occ for occ in occurrences if occ.kind == "due"]
        self.assertEqual(len(plan_occurrences), 3)
        self.assertEqual(len(due_occurrences), 1)
        self.assertEqual(due_occurrences[0].start, self.due)
        self.assertEqual(
            [occ.start.day for occ in plan_occurrences],
            [20, 22, 24],
        )
        # 三个计划时间属于同一个任务，并且带有序号信息
        self.assertEqual({occ.task_id for occ in plan_occurrences}, {self.task_id})
        self.assertEqual([occ.plan_index for occ in plan_occurrences], [1, 2, 3])
        self.assertTrue(all(occ.plan_total == 3 for occ in plan_occurrences))
        self.assertEqual(occurrences, sorted(occurrences, key=lambda occ: occ.start))

    def test_occurrences_outside_week_are_hidden(self) -> None:
        occurrences = self.env.service.occurrences(self.due.date() + timedelta(days=14))
        self.assertEqual(occurrences, [])

    def test_mark_done_and_reopen(self) -> None:
        task = self.env.service.set_status(self.task_id, "done")
        self.assertEqual(task.status, "done")
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(self.env.pending(), [])
        self.assertFalse(task.is_overdue())

        reopened = self.env.service.set_status(self.task_id, "todo")
        self.assertIsNone(reopened.completed_at)
        self.assertTrue(len(self.env.pending()) >= 1)

    def test_toggle_done(self) -> None:
        self.assertEqual(self.env.service.toggle_done(self.task_id).status, "done")
        self.assertEqual(self.env.service.toggle_done(self.task_id).status, "todo")

    def test_week_summary(self) -> None:
        summary = self.env.service.week_summary(week_start_of(self.due.date()))
        self.assertEqual(summary.total_tasks, 1)
        self.assertEqual(summary.week_events, 4)
        self.assertEqual(summary.done, 0)

    def test_overdue_detection(self) -> None:
        past = datetime.now() - timedelta(days=2)
        task_id = self.env.create_task(title="过期任务", due_at=past)
        task = self.env.service.get_task(task_id)
        self.assertTrue(task.is_overdue())
        overdue = self.env.service.overdue_tasks()
        self.assertIn(task_id, [int(t.id or 0) for t in overdue])
        self.assertIn("逾期", task.overdue_label())

    def test_completed_task_is_not_overdue(self) -> None:
        past = datetime.now() - timedelta(days=2)
        task_id = self.env.create_task(title="已完成过期", due_at=past, status="done")
        task = self.env.service.get_task(task_id)
        self.assertFalse(task.is_overdue())
        self.assertEqual(self.env.service.overdue_tasks(), [])


class SearchAndFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("filter")
        now = datetime.now()
        self.env.create_task(
            title="完成课程报告",
            due_at=now + timedelta(days=2),
            category="学习",
            priority="urgent",
            description="城市公共空间",
        )
        self.env.create_task(
            title="团队周会",
            due_at=now + timedelta(days=1),
            category="工作",
            priority="normal",
            status="doing",
        )
        self.env.create_task(
            title="买牛奶",
            due_at=now - timedelta(days=1),
            category="生活",
            priority="important",
        )
        self.env.create_task(
            title="阅读笔记",
            due_at=now + timedelta(days=3),
            category="学习",
            status="done",
            notes="第三章",
        )

    def tearDown(self) -> None:
        self.env.close()

    def test_search_by_title(self) -> None:
        hits = self.env.service.search_tasks("课程")
        self.assertEqual([task.title for task in hits], ["完成课程报告"])
        self.assertEqual(self.env.service.search_tasks("不存在的关键字"), [])

    def test_search_matches_description_and_notes(self) -> None:
        self.assertEqual([t.title for t in self.env.service.search_tasks("公共空间")], ["完成课程报告"])
        self.assertEqual([t.title for t in self.env.service.search_tasks("第三章")], ["阅读笔记"])

    def test_filter_by_category(self) -> None:
        tasks = self.env.service.list_tasks(TaskFilter(category="学习"))
        self.assertEqual(len(tasks), 2)

    def test_filter_by_status(self) -> None:
        self.assertEqual(len(self.env.service.list_tasks(TaskFilter(status="done"))), 1)
        self.assertEqual(len(self.env.service.list_tasks(TaskFilter(status="doing"))), 1)

    def test_filter_by_priority(self) -> None:
        tasks = self.env.service.list_tasks(TaskFilter(priority="urgent"))
        self.assertEqual([t.title for t in tasks], ["完成课程报告"])

    def test_filter_overdue_only(self) -> None:
        tasks = self.env.service.list_tasks(TaskFilter(overdue_only=True))
        self.assertEqual([t.title for t in tasks], ["买牛奶"])

    def test_combined_search_and_filter(self) -> None:
        tasks = self.env.service.list_tasks(TaskFilter(search="报告", category="学习", priority="urgent"))
        self.assertEqual(len(tasks), 1)
        tasks = self.env.service.list_tasks(TaskFilter(search="报告", category="工作"))
        self.assertEqual(tasks, [])

    def test_categories_merge_config_and_used(self) -> None:
        categories = self.env.service.categories()
        self.assertEqual(categories[:3], ["学习", "工作", "生活"])


class DuplicateAndDeleteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = TestEnv("copy")

    def tearDown(self) -> None:
        self.env.close()

    def test_duplicate_task(self) -> None:
        due = datetime(2026, 10, 25, 18, 0)
        task_id = self.env.create_task(
            title="原始任务",
            due_at=due,
            plans=[
                PlanDraft(plan_at=due - timedelta(days=2), label="计划一"),
                PlanDraft(plan_at=due - timedelta(days=1), label="计划二", remind_enabled=True),
            ],
            status="done",
        )
        copy = self.env.service.duplicate_task(task_id)
        self.assertNotEqual(copy.id, task_id)
        self.assertEqual(copy.title, "原始任务（副本）")
        self.assertEqual(copy.due_at, due)
        self.assertEqual(copy.status, "todo")
        self.assertEqual(len(copy.plans), 2)
        self.assertTrue(copy.plans[1].remind_enabled)
        self.assertEqual(self.env.task_count(), 2)

    def test_delete_task_clears_plans_and_reminders(self) -> None:
        task_id = self.env.create_task(
            title="将被删除",
            plans=[PlanDraft(plan_at=datetime.now() + timedelta(days=1), remind_enabled=True)],
        )
        self.assertGreater(len(self.env.pending()), 0)
        self.env.service.delete_task(task_id)
        self.assertEqual(self.env.task_count(), 0)
        self.assertEqual(self.env.db.scalar("SELECT COUNT(*) FROM plan_times"), 0)
        self.assertEqual(self.env.db.scalar("SELECT COUNT(*) FROM reminders"), 0)

    def test_deleting_twice_is_safe(self) -> None:
        task_id = self.env.create_task(title="重复删除")
        self.env.service.delete_task(task_id)
        self.env.service.delete_task(task_id)  # 不应抛异常
        self.assertNotIn(task_id, [int(t.id or 0) for t in self.env.service.list_tasks()])


if __name__ == "__main__":
    unittest.main()
