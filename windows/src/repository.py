"""任务读取辅助：把数据库行转换成模型对象（供服务层与提醒引擎共用）。"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Mapping, Sequence

from .database import Database
from .models import PlanTime, Reminder, Task


def _group_plans(rows: Iterable[sqlite3.Row]) -> dict[int, list[PlanTime]]:
    grouped: dict[int, list[PlanTime]] = {}
    for row in rows:
        plan = PlanTime.from_row(row)
        grouped.setdefault(int(row["task_id"]), []).append(plan)
    return grouped


def attach_plans(db: Database, tasks: list[Task]) -> list[Task]:
    if not tasks:
        return tasks
    ids = [int(t.id) for t in tasks if t.id is not None]
    if not ids:
        return tasks
    placeholders = ",".join("?" for _ in ids)
    rows = db.query(
        f"SELECT * FROM plan_times WHERE task_id IN ({placeholders}) ORDER BY plan_at, sort_order, id",
        ids,
    )
    grouped = _group_plans(rows)
    for task in tasks:
        task.plans = grouped.get(int(task.id), [])
    return tasks


def fetch_task(db: Database, task_id: int) -> Task | None:
    row = db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if row is None:
        return None
    task = Task.from_row(row)
    plans = db.query(
        "SELECT * FROM plan_times WHERE task_id = ? ORDER BY plan_at, sort_order, id",
        (task_id,),
    )
    task.plans = [PlanTime.from_row(plan) for plan in plans]
    return task


def fetch_tasks(
    db: Database,
    *,
    where: str = "",
    params: Sequence[object] = (),
    order: str = "due_at ASC, id ASC",
    limit: int | None = None,
) -> list[Task]:
    sql = "SELECT * FROM tasks"
    if where:
        sql += f" WHERE {where}"
    sql += f" ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.query(sql, params)
    tasks = [Task.from_row(row) for row in rows]
    return attach_plans(db, tasks)


def fetch_plan(db: Database, plan_id: int) -> PlanTime | None:
    row = db.query_one("SELECT * FROM plan_times WHERE id = ?", (plan_id,))
    return PlanTime.from_row(row) if row is not None else None


def fetch_reminder(db: Database, reminder_id: int) -> Reminder | None:
    row = db.query_one("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    return Reminder.from_row(row) if row is not None else None


def task_row_to_task(row: Mapping[str, object]) -> Task:
    return Task.from_row(row)  # type: ignore[arg-type]
