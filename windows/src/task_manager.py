"""任务服务层（业务逻辑，不依赖 Qt）。

窗口、托盘、提醒调度都调用这里，保证只有一处写库逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Sequence

from . import repository
from .database import Database
from .logging_setup import get_logger
from .models import (
    DEFAULT_CATEGORIES,
    KIND_DUE,
    KIND_PLAN,
    PRIORITY_NORMAL,
    STATUS_DONE,
    STATUS_TODO,
    Occurrence,
    PlanDraft,
    PlanTime,
    Task,
    TaskDraft,
    sort_tasks,
    status_label,
)
from .settings_store import SettingsStore
from .time_utils import end_of_day, format_dt, start_of_day, week_bounds

logger = get_logger("service")

PLAN_DURATION_MINUTES = 45
DUE_DURATION_MINUTES = 30

# 用于区分「没有传这个参数」和「显式传 None（清空结束时间）」
_UNSET = object()


def _plan_intersects(plan: PlanTime, start: datetime, end: datetime) -> bool:
    """计划时间（可能跨天）是否与给定时间范围有交集。"""
    if plan.end_at is None:
        return start <= plan.plan_at <= end
    return plan.plan_at <= end and plan.end_at >= start


def _validate_plan_range(plan_at: datetime, end_at: datetime | None) -> None:
    if end_at is not None and end_at <= plan_at:
        raise ValidationError("计划的结束时间必须晚于开始时间。")


class ValidationError(ValueError):
    """用户输入不合法。"""


class TaskNotFoundError(LookupError):
    pass


@dataclass
class TaskFilter:
    search: str = ""
    category: str = ""
    status: str = ""
    priority: str = ""
    overdue_only: bool = False
    due_from: datetime | None = None
    due_to: datetime | None = None

    def matches(self, task: Task, now: datetime) -> bool:
        if self.search:
            needle = self.search.strip().lower()
            if needle and needle not in task.search_blob():
                return False
        if self.category and task.category != self.category:
            return False
        if self.status and task.status != self.status:
            return False
        if self.priority and task.priority != self.priority:
            return False
        if self.overdue_only and not task.is_overdue(now):
            return False
        if self.due_from and task.due_at < self.due_from:
            return False
        if self.due_to and task.due_at > self.due_to:
            return False
        return True

    @property
    def is_active(self) -> bool:
        return bool(
            self.search
            or self.category
            or self.status
            or self.priority
            or self.overdue_only
            or self.due_from
            or self.due_to
        )


@dataclass
class WeekSummary:
    total_tasks: int = 0
    week_events: int = 0
    done: int = 0
    overdue: int = 0
    pending_reminders: int = 0


@dataclass
class SearchHit:
    task: Task
    reason: str
    in_current_week: bool = False


class PlannerService:
    def __init__(self, db: Database, settings: SettingsStore, engine=None) -> None:
        self.db = db
        self.settings = settings
        self.engine = engine  # ReminderEngine | None，通过 attach_engine 注入避免循环依赖

    # ------------------------------------------------------------------
    def attach_engine(self, engine) -> None:
        self.engine = engine

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get_task(self, task_id: int) -> Task:
        task = repository.fetch_task(self.db, task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在（id={task_id}）")
        return task

    def list_tasks(self, filters: TaskFilter | None = None, now: datetime | None = None) -> list[Task]:
        now = now or datetime.now()
        filters = filters or TaskFilter()
        tasks = repository.fetch_tasks(self.db, order="due_at ASC, id ASC")
        result = [task for task in tasks if filters.matches(task, now)]
        return sort_tasks(result)

    def search_tasks(self, needle: str, now: datetime | None = None, limit: int = 100) -> list[Task]:
        now = now or datetime.now()
        needle = needle.strip().lower()
        if not needle:
            return []
        tasks = repository.fetch_tasks(self.db, order="due_at ASC, id ASC")
        hits = [task for task in tasks if needle in task.search_blob()]
        return sort_tasks(hits)[:limit]

    def overdue_tasks(self, now: datetime | None = None) -> list[Task]:
        now = now or datetime.now()
        tasks = repository.fetch_tasks(
            self.db, where="status != ? AND due_at <= ?", params=(STATUS_DONE, format_dt(now))
        )
        return sort_tasks(tasks)

    def categories(self) -> list[str]:
        configured = self.settings.categories
        used = [
            row["category"]
            for row in self.db.query("SELECT DISTINCT category FROM tasks ORDER BY category")
            if row["category"]
        ]
        merged: list[str] = list(configured)
        for name in used:
            if name not in merged:
                merged.append(name)
        return merged

    # ------------------------------------------------------------------
    # 写入：任务
    # ------------------------------------------------------------------
    def _validate(self, draft: TaskDraft) -> TaskDraft:
        title = (draft.title or "").strip()
        if not title:
            raise ValidationError("任务名称不能为空。")
        if draft.due_at is None:
            raise ValidationError("请选择截止日期和时间。")
        category = (draft.category or DEFAULT_CATEGORIES[0]).strip() or DEFAULT_CATEGORIES[0]
        priorities = {"normal", "important", "urgent"}
        statuses = {"todo", "doing", "done"}
        return replace(
            draft,
            title=title,
            category=category,
            priority=draft.priority if draft.priority in priorities else PRIORITY_NORMAL,
            status=draft.status if draft.status in statuses else STATUS_TODO,
        )

    def create_task(self, draft: TaskDraft) -> Task:
        draft = self._validate(draft)
        now_text = format_dt(datetime.now())
        completed_at = now_text if draft.status == STATUS_DONE else None
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks(title, description, due_at, category, priority, status,"
                " remind_due, notes, completed_at, overdue_notified, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,0,?,?)",
                (
                    draft.title,
                    draft.description or "",
                    format_dt(draft.due_at),
                    draft.category,
                    draft.priority,
                    draft.status,
                    1 if draft.remind_due else 0,
                    draft.notes or "",
                    completed_at,
                    now_text,
                    now_text,
                ),
            )
            task_id = int(cursor.lastrowid or 0)
            self._insert_plans(conn, task_id, draft.plans)
        task = self.get_task(task_id)
        self._sync_reminders(task)
        logger.info("创建任务 #%s：%s", task_id, task.title)
        return task

    @staticmethod
    def _insert_plans(conn, task_id: int, plans: Sequence[PlanDraft]) -> None:
        for index, plan in enumerate(sorted(plans, key=lambda p: p.plan_at)):
            _validate_plan_range(plan.plan_at, plan.end_at)
            remind_start = plan.start_reminder
            conn.execute(
                "INSERT INTO plan_times(task_id, plan_at, end_at, label, remind_enabled,"
                " remind_start, remind_end, remind_lead_minutes, done, sort_order)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    format_dt(plan.plan_at),
                    format_dt(plan.end_at) if plan.end_at is not None else None,
                    (plan.label or "").strip(),
                    1 if remind_start else 0,
                    1 if remind_start else 0,
                    1 if plan.remind_end else 0,
                    max(0, int(plan.remind_lead_minutes)),
                    1 if plan.done else 0,
                    index,
                ),
            )

    def update_task(self, task_id: int, draft: TaskDraft) -> Task:
        draft = self._validate(draft)
        existing = self.get_task(task_id)
        now_text = format_dt(datetime.now())
        due_changed = format_dt(existing.due_at) != format_dt(draft.due_at)
        becoming_done = draft.status == STATUS_DONE and existing.status != STATUS_DONE
        reopened = draft.status != STATUS_DONE and existing.status == STATUS_DONE
        completed_at = existing.completed_at
        if becoming_done:
            completed_at = now_text
        elif reopened:
            completed_at = None

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE tasks SET title = ?, description = ?, due_at = ?, category = ?,"
                " priority = ?, status = ?, remind_due = ?, notes = ?, completed_at = ?,"
                " updated_at = ?, overdue_notified = CASE WHEN ? = 1 THEN 0 ELSE overdue_notified END"
                " WHERE id = ?",
                (
                    draft.title,
                    draft.description or "",
                    format_dt(draft.due_at),
                    draft.category,
                    draft.priority,
                    draft.status,
                    1 if draft.remind_due else 0,
                    draft.notes or "",
                    completed_at,
                    now_text,
                    1 if due_changed else 0,
                    task_id,
                ),
            )
            self._reconcile_plans(conn, task_id, draft.plans)
        task = self.get_task(task_id)
        self._sync_reminders(task, cancel_first=due_changed or becoming_done)
        logger.info("更新任务 #%s：%s", task_id, task.title)
        return task

    @staticmethod
    def _reconcile_plans(conn, task_id: int, drafts: Sequence[PlanDraft]) -> None:
        """只增删改差异部分——单独删除某个计划时间不会影响其它计划时间。"""
        existing_rows = conn.execute(
            "SELECT id FROM plan_times WHERE task_id = ?", (task_id,)
        ).fetchall()
        existing_ids = {int(row["id"]) for row in existing_rows}
        keep_ids = {int(plan.id) for plan in drafts if plan.id is not None}
        for stale in existing_ids - keep_ids:
            conn.execute("DELETE FROM plan_times WHERE id = ?", (stale,))
        for index, plan in enumerate(sorted(drafts, key=lambda p: p.plan_at)):
            _validate_plan_range(plan.plan_at, plan.end_at)
            remind_start = plan.start_reminder
            values = (
                format_dt(plan.plan_at),
                format_dt(plan.end_at) if plan.end_at is not None else None,
                (plan.label or "").strip(),
                1 if remind_start else 0,
                1 if remind_start else 0,
                1 if plan.remind_end else 0,
                max(0, int(plan.remind_lead_minutes)),
                1 if plan.done else 0,
                index,
            )
            if plan.id is not None and int(plan.id) in existing_ids:
                conn.execute(
                    "UPDATE plan_times SET plan_at = ?, end_at = ?, label = ?,"
                    " remind_enabled = ?, remind_start = ?, remind_end = ?,"
                    " remind_lead_minutes = ?, done = ?, sort_order = ? WHERE id = ?",
                    values + (int(plan.id),),
                )
            else:
                # 新增的计划时间（plan.id 为 None，或来自别的任务）
                conn.execute(
                    "INSERT INTO plan_times(task_id, plan_at, end_at, label, remind_enabled,"
                    " remind_start, remind_end, remind_lead_minutes, done, sort_order)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (task_id,) + values,
                )

    # ------------------------------------------------------------------
    # 写入：计划时间（独立操作）
    # ------------------------------------------------------------------
    def add_plan(
        self,
        task_id: int,
        plan_at: datetime,
        label: str = "",
        remind_enabled: bool = False,
        remind_lead_minutes: int = 10,
        *,
        end_at: datetime | None = None,
        remind_start: bool | None = None,
        remind_end: bool = False,
    ) -> PlanTime:
        remind_start_enabled = remind_enabled if remind_start is None else remind_start
        _validate_plan_range(plan_at, end_at)
        task = self.get_task(task_id)
        order = len(task.plans)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO plan_times(task_id, plan_at, end_at, label, remind_enabled,"
                " remind_start, remind_end, remind_lead_minutes, done, sort_order)"
                " VALUES (?,?,?,?,?,?,?,?,0,?)",
                (
                    task_id,
                    format_dt(plan_at),
                    format_dt(end_at) if end_at is not None else None,
                    label.strip(),
                    1 if remind_start_enabled else 0,
                    1 if remind_start_enabled else 0,
                    1 if (remind_end and end_at is not None) else 0,
                    max(0, int(remind_lead_minutes)),
                    order,
                ),
            )
            plan_id = int(cursor.lastrowid or 0)
        self._sync_reminders_by_id(task_id)
        return repository.fetch_plan(self.db, plan_id)  # type: ignore[return-value]

    def update_plan(
        self,
        plan_id: int,
        *,
        plan_at: datetime | None = None,
        label: str | None = None,
        remind_enabled: bool | None = None,
        remind_lead_minutes: int | None = None,
        done: bool | None = None,
        end_at: object = _UNSET,
        remind_start: bool | None = None,
        remind_end: bool | None = None,
    ) -> PlanTime:
        plan = repository.fetch_plan(self.db, plan_id)
        if plan is None:
            raise TaskNotFoundError(f"计划时间不存在（id={plan_id}）")
        changes = []
        params: list[object] = []
        if plan_at is not None:
            changes.append("plan_at = ?")
            params.append(format_dt(plan_at))
        if end_at is not _UNSET:
            end_value = end_at if isinstance(end_at, datetime) else None
            changes.append("end_at = ?")
            params.append(format_dt(end_value) if end_value is not None else None)
        if label is not None:
            changes.append("label = ?")
            params.append(label.strip())
        start_flag = remind_start if remind_start is not None else remind_enabled
        if start_flag is not None:
            changes.append("remind_enabled = ?")
            params.append(1 if start_flag else 0)
            changes.append("remind_start = ?")
            params.append(1 if start_flag else 0)
        if remind_end is not None:
            changes.append("remind_end = ?")
            params.append(1 if remind_end else 0)
        if remind_lead_minutes is not None:
            changes.append("remind_lead_minutes = ?")
            params.append(max(0, int(remind_lead_minutes)))
        if done is not None:
            changes.append("done = ?")
            params.append(1 if done else 0)
        if not changes:
            return plan
        # 校验「结束晚于开始」，用更新后的最终值判断
        final_start = plan_at if plan_at is not None else plan.plan_at
        if end_at is not _UNSET:
            final_end = end_at if isinstance(end_at, datetime) else None
        else:
            final_end = plan.end_at
        _validate_plan_range(final_start, final_end)
        params.append(plan_id)
        with self.db.transaction() as conn:
            conn.execute(f"UPDATE plan_times SET {', '.join(changes)} WHERE id = ?", params)
        self._sync_reminders_by_id(int(plan.task_id or 0))
        return repository.fetch_plan(self.db, plan_id)  # type: ignore[return-value]

    def delete_plan(self, plan_id: int) -> None:
        plan = repository.fetch_plan(self.db, plan_id)
        if plan is None:
            return
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM plan_times WHERE id = ?", (plan_id,))
        self._sync_reminders_by_id(int(plan.task_id or 0))

    def set_plan_done(self, plan_id: int, done: bool) -> PlanTime:
        return self.update_plan(plan_id, done=done)

    # ------------------------------------------------------------------
    # 状态 / 删除 / 复制
    # ------------------------------------------------------------------
    def set_status(self, task_id: int, status: str) -> Task:
        task = self.get_task(task_id)
        if status not in {"todo", "doing", "done"}:
            raise ValidationError(f"未知状态：{status}")
        now_text = format_dt(datetime.now())
        with self.db.transaction() as conn:
            if status == STATUS_DONE:
                conn.execute(
                    "UPDATE tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                    (status, now_text, now_text, task_id),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET status = ?, completed_at = NULL, updated_at = ? WHERE id = ?",
                    (status, now_text, task_id),
                )
        task = self.get_task(task_id)
        self._sync_reminders(task, cancel_first=True)
        logger.info("任务 #%s 状态改为 %s", task_id, status_label(status))
        return task

    def toggle_done(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        return self.set_status(task_id, STATUS_TODO if task.status == STATUS_DONE else STATUS_DONE)

    def delete_task(self, task_id: int) -> None:
        task = repository.fetch_task(self.db, task_id)
        if task is None:
            return
        if self.engine is not None:
            self.engine.cancel_pending(task_id)
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM plan_times WHERE task_id = ?", (task_id,))
            conn.execute("DELETE FROM reminders WHERE task_id = ?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        logger.info("删除任务 #%s：%s", task_id, task.title)

    def duplicate_task(self, task_id: int, shift: timedelta | None = None) -> Task:
        task = self.get_task(task_id)
        shift = shift or timedelta(0)
        draft = TaskDraft.from_task(task)
        draft.title = f"{task.title}（副本）"
        draft.status = STATUS_TODO
        draft.due_at = task.due_at + shift
        draft.plans = [
            PlanDraft(
                id=None,
                plan_at=plan.plan_at + shift,
                label=plan.label,
                remind_enabled=plan.remind_start,
                remind_start=plan.remind_start,
                remind_lead_minutes=plan.remind_lead_minutes,
                done=False,
                end_at=(plan.end_at + shift) if plan.end_at is not None else None,
                remind_end=plan.remind_end,
            )
            for plan in task.sorted_plans()
        ]
        return self.create_task(draft)

    # ------------------------------------------------------------------
    # 提醒联动
    # ------------------------------------------------------------------
    def _sync_reminders(self, task: Task, *, cancel_first: bool = False) -> None:
        if self.engine is None:
            return
        if cancel_first:
            self.engine.cancel_pending(int(task.id or 0))
        self.engine.sync_task(task)

    def _sync_reminders_by_id(self, task_id: int) -> None:
        if self.engine is not None:
            self.engine.sync_task_by_id(task_id)

    def preview_due_reminder(self, task: Task) -> datetime | None:
        if not task.remind_due:
            return None
        from .reminder_scheduler import compute_due_reminder

        return compute_due_reminder(task.due_at, self.settings.reminder_policy())

    # ------------------------------------------------------------------
    # 周视图数据
    # ------------------------------------------------------------------
    def occurrences(
        self,
        week_start: date,
        filters: TaskFilter | None = None,
        now: datetime | None = None,
    ) -> list[Occurrence]:
        now = now or datetime.now()
        filters = filters or TaskFilter()
        start = start_of_day(week_start)
        end = end_of_day(week_start + timedelta(days=6))
        tasks = self.list_tasks(filters, now=now)
        result: list[Occurrence] = []
        for task in tasks:
            index_total = len(task.plans)
            for order, plan in enumerate(task.sorted_plans(), start=1):
                if not _plan_intersects(plan, start, end):
                    continue
                # 有结束时间就按真实起止绘制；旧计划保持原来的固定时长短块
                duration = PLAN_DURATION_MINUTES
                if plan.end_at is not None:
                    duration = max(1, int((plan.end_at - plan.plan_at).total_seconds() // 60))
                result.append(
                    Occurrence(
                        task_id=int(task.id or 0),
                        title=task.title,
                        kind=KIND_PLAN,
                        start=plan.plan_at,
                        task=task,
                        plan=plan,
                        plan_index=order,
                        plan_total=index_total,
                        duration_minutes=duration,
                        end_at=plan.end_at,
                    )
                )
            if start <= task.due_at <= end:
                result.append(
                    Occurrence(
                        task_id=int(task.id or 0),
                        title=task.title,
                        kind=KIND_DUE,
                        start=task.due_at,
                        task=task,
                        duration_minutes=DUE_DURATION_MINUTES,
                    )
                )
        result.sort(key=lambda occ: (occ.start, occ.kind == KIND_DUE, occ.title))
        return result

    def week_summary(self, week_start: date, filters: TaskFilter | None = None) -> WeekSummary:
        now = datetime.now()
        monday, sunday = week_bounds(week_start)
        start = start_of_day(monday)
        end = end_of_day(sunday)
        tasks = self.list_tasks(filters, now=now)
        events = 0
        done = 0
        for task in tasks:
            in_week = False
            if start <= task.due_at <= end:
                events += 1
                in_week = True
            for plan in task.plans:
                if _plan_intersects(plan, start, end):
                    events += 1
                    in_week = True
            if in_week and task.is_done:
                done += 1
        overdue = len(self.overdue_tasks(now))
        return WeekSummary(
            total_tasks=len(tasks),
            week_events=events,
            done=done,
            overdue=overdue,
            pending_reminders=self.engine.pending_count() if self.engine else 0,
        )

    # ------------------------------------------------------------------
    # 导入导出
    # ------------------------------------------------------------------
    def export_csv(self, path: str) -> int:
        return self.db.export_csv(path)

    def import_csv(self, path: str) -> dict[str, int]:
        result = self.db.import_csv(path)
        if self.engine is not None:
            self.engine.rebuild_all()
        return result

    def backup_to(self, path: str) -> None:
        self.db.backup_to(path)

    def restore_from(self, path: str) -> None:
        self.db.restore_from(path)
        if self.engine is not None:
            self.engine.rebuild_all()
