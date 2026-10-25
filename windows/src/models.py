"""领域模型。

全部为纯 Python 数据类，不依赖 Qt，方便单元测试。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from .time_utils import format_dt, parse_dt, remaining_label

# --------------------------------------------------------------------------
# 枚举元数据
# --------------------------------------------------------------------------
PRIORITY_NORMAL = "normal"
PRIORITY_IMPORTANT = "important"
PRIORITY_URGENT = "urgent"

PRIORITIES: tuple[tuple[str, str], ...] = (
    (PRIORITY_NORMAL, "普通"),
    (PRIORITY_IMPORTANT, "重要"),
    (PRIORITY_URGENT, "紧急"),
)
PRIORITY_LABELS = dict(PRIORITIES)
PRIORITY_ORDER = {key: index for index, (key, _) in enumerate(PRIORITIES)}

PRIORITY_COLORS = {
    PRIORITY_NORMAL: "#94A3BE",
    PRIORITY_IMPORTANT: "#D79A38",
    PRIORITY_URGENT: "#D96A72",
}

STATUS_TODO = "todo"
STATUS_DOING = "doing"
STATUS_DONE = "done"

STATUSES: tuple[tuple[str, str], ...] = (
    (STATUS_TODO, "未开始"),
    (STATUS_DOING, "进行中"),
    (STATUS_DONE, "已完成"),
)
STATUS_LABELS = dict(STATUSES)
STATUS_ORDER = {key: index for index, (key, _) in enumerate(STATUSES)}

STATUS_COLORS = {
    STATUS_TODO: "#94A3BE",
    STATUS_DOING: "#5B8DEF",
    STATUS_DONE: "#63B38A",
}

DEFAULT_CATEGORIES = ("学习", "工作", "生活")
CATEGORY_COLORS = {
    "学习": "#6C8AE4",
    "工作": "#D79A38",
    "生活": "#63B38A",
}
_CATEGORY_FALLBACK = ("#A78BFA", "#38BDF8", "#F472B6", "#34D399", "#FBBF24", "#818CF8")

KIND_PLAN = "plan"
KIND_DUE = "due"
KIND_OVERDUE = "overdue"


def category_color(name: str) -> str:
    if name in CATEGORY_COLORS:
        return CATEGORY_COLORS[name]
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    return _CATEGORY_FALLBACK[int(digest[:4], 16) % len(_CATEGORY_FALLBACK)]


def priority_label(value: str) -> str:
    return PRIORITY_LABELS.get(value, value)


def status_label(value: str) -> str:
    return STATUS_LABELS.get(value, value)


# --------------------------------------------------------------------------
# 计划时间
# --------------------------------------------------------------------------
@dataclass
class PlanTime:
    """任务下的一个计划时间（一个任务可以有 0..N 个）。"""

    id: int | None = None
    task_id: int | None = None
    plan_at: datetime = field(default_factory=datetime.now)
    label: str = ""
    remind_enabled: bool = False
    remind_lead_minutes: int = 10
    done: bool = False
    sort_order: int = 0

    def reminder_at(self) -> datetime | None:
        if not self.remind_enabled:
            return None
        return self.plan_at - timedelta(minutes=self.remind_lead_minutes)

    @property
    def time_text(self) -> str:
        return self.plan_at.strftime("%H:%M")

    @property
    def date_text(self) -> str:
        return self.plan_at.strftime("%Y-%m-%d")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "PlanTime":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            plan_at=parse_dt(row["plan_at"]) or datetime.now(),
            label=row["label"] or "",
            remind_enabled=bool(row["remind_enabled"]),
            remind_lead_minutes=int(row["remind_lead_minutes"]),
            done=bool(row["done"]),
            sort_order=int(row["sort_order"]),
        )


# --------------------------------------------------------------------------
# 任务
# --------------------------------------------------------------------------
@dataclass
class Task:
    id: int | None = None
    title: str = ""
    description: str = ""
    due_at: datetime = field(default_factory=datetime.now)
    category: str = DEFAULT_CATEGORIES[0]
    priority: str = PRIORITY_NORMAL
    status: str = STATUS_TODO
    remind_due: bool = True
    notes: str = ""
    completed_at: datetime | None = None
    overdue_notified: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    plans: list[PlanTime] = field(default_factory=list)

    # -- 派生状态 ---------------------------------------------------------
    @property
    def is_done(self) -> bool:
        return self.status == STATUS_DONE

    def is_overdue(self, reference: datetime | None = None) -> bool:
        ref = reference or datetime.now()
        return (not self.is_done) and self.due_at < ref

    def overdue_label(self, reference: datetime | None = None) -> str:
        ref = reference or datetime.now()
        return f"逾期 {remaining_label(self.due_at, ref).replace('已逾期 ', '')}"

    def due_text(self) -> str:
        return self.due_at.strftime("%Y-%m-%d %H:%M")

    def short_due(self) -> str:
        return self.due_at.strftime("%m-%d %H:%M")

    def sorted_plans(self) -> list[PlanTime]:
        return sorted(self.plans, key=lambda p: (p.plan_at, p.sort_order, p.id or 0))

    def plan_index(self, plan_id: int | None) -> tuple[int, int]:
        """返回 (序号, 总数)，用于在周视图标注「第几个计划时间」。"""
        plans = self.sorted_plans()
        total = len(plans)
        for index, plan in enumerate(plans, start=1):
            if plan.id == plan_id:
                return index, total
        return 0, total

    def group_hint(self) -> str:
        if len(self.plans) <= 1:
            return ""
        parts = [f"{p.plan_at.strftime('%m-%d %H:%M')} {p.label}".strip() for p in self.sorted_plans()]
        return "本任务共 {} 个计划时间：\n".format(len(parts)) + "\n".join(f"· {item}" for item in parts)

    def search_blob(self) -> str:
        return " ".join(
            [
                self.title,
                self.description,
                self.notes,
                self.category,
                priority_label(self.priority),
                status_label(self.status),
            ]
        ).lower()

    @classmethod
    def from_row(cls, row: Mapping[str, Any], plans: Iterable[PlanTime] = ()) -> "Task":
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            due_at=parse_dt(row["due_at"]) or datetime.now(),
            category=row["category"] or DEFAULT_CATEGORIES[0],
            priority=row["priority"] or PRIORITY_NORMAL,
            status=row["status"] or STATUS_TODO,
            remind_due=bool(row["remind_due"]),
            notes=row["notes"] or "",
            completed_at=parse_dt(row["completed_at"]),
            overdue_notified=bool(row["overdue_notified"]),
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
            plans=list(plans),
        )


# --------------------------------------------------------------------------
# 提醒
# --------------------------------------------------------------------------
REMINDER_PENDING = "pending"
REMINDER_SENT = "sent"
REMINDER_SKIPPED = "skipped"
REMINDER_CANCELLED = "cancelled"


@dataclass
class Reminder:
    id: int | None = None
    task_id: int = 0
    kind: str = KIND_DUE
    plan_id: int | None = None
    fire_at: datetime = field(default_factory=datetime.now)
    status: str = REMINDER_PENDING
    fired_at: datetime | None = None
    snooze_count: int = 0
    anchor_at: str = ""
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Reminder":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            kind=row["kind"],
            plan_id=row["plan_id"],
            fire_at=parse_dt(row["fire_at"]) or datetime.now(),
            status=row["status"],
            fired_at=parse_dt(row["fired_at"]),
            snooze_count=int(row["snooze_count"] or 0),
            anchor_at=row["anchor_at"] or "",
            created_at=parse_dt(row["created_at"]),
        )


@dataclass
class ReminderSpec:
    """由任务推导出的「应当存在的提醒」。"""

    task_id: int
    kind: str
    plan_id: int | None
    fire_at: datetime
    anchor_at: str

    @property
    def key(self) -> tuple[int, str, int | None, str]:
        return (self.task_id, self.kind, self.plan_id, self.anchor_at)


# --------------------------------------------------------------------------
# 周视图出现项
# --------------------------------------------------------------------------
@dataclass
class Occurrence:
    """周视图里的一个时间块：可能属于计划时间，也可能是截止时间。"""

    task_id: int
    title: str
    kind: str
    start: datetime
    task: Task
    plan: PlanTime | None = None
    plan_index: int = 0
    plan_total: int = 0
    duration_minutes: int = 45

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.kind, self.task_id, self.plan.id if self.plan else 0)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def is_done(self) -> bool:
        if self.kind == KIND_PLAN and self.plan is not None:
            return self.plan.done or self.task.is_done
        return self.task.is_done

    def is_overdue(self, reference: datetime | None = None) -> bool:
        return self.kind in (KIND_DUE, KIND_OVERDUE) and self.task.is_overdue(reference)

    @property
    def detail_text(self) -> str:
        if self.kind == KIND_PLAN and self.plan is not None:
            bits = [f"计划 {self.plan.plan_at.strftime('%H:%M')}"]
            if self.plan.label:
                bits.append(self.plan.label)
            if self.plan.remind_enabled:
                bits.append(f"提前 {self.plan.remind_lead_minutes} 分钟提醒")
            if self.plan_index:
                bits.append(f"第 {self.plan_index}/{self.plan_total} 个计划时间")
            return " · ".join(bits)
        return "截止 " + self.task.due_at.strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------
# 草稿（对话框 -> 服务层）
# --------------------------------------------------------------------------
@dataclass
class PlanDraft:
    id: int | None = None
    plan_at: datetime = field(default_factory=datetime.now)
    label: str = ""
    remind_enabled: bool = False
    remind_lead_minutes: int = 10
    done: bool = False


@dataclass
class TaskDraft:
    title: str = ""
    description: str = ""
    due_at: datetime = field(default_factory=datetime.now)
    category: str = DEFAULT_CATEGORIES[0]
    priority: str = PRIORITY_NORMAL
    status: str = STATUS_TODO
    remind_due: bool = True
    notes: str = ""
    plans: list[PlanDraft] = field(default_factory=list)

    def to_task(self) -> Task:
        return Task(
            title=self.title.strip(),
            description=self.description,
            due_at=self.due_at,
            category=self.category,
            priority=self.priority,
            status=self.status,
            remind_due=self.remind_due,
            notes=self.notes,
        )

    @classmethod
    def from_task(cls, task: Task) -> "TaskDraft":
        return cls(
            title=task.title,
            description=task.description,
            due_at=task.due_at,
            category=task.category,
            priority=task.priority,
            status=task.status,
            remind_due=task.remind_due,
            notes=task.notes,
            plans=[
                PlanDraft(
                    id=plan.id,
                    plan_at=plan.plan_at,
                    label=plan.label,
                    remind_enabled=plan.remind_enabled,
                    remind_lead_minutes=plan.remind_lead_minutes,
                    done=plan.done,
                )
                for plan in task.sorted_plans()
            ],
        )


def sort_tasks(tasks: Iterable[Task]) -> list[Task]:
    """按「截止时间、优先级」排序，已完成沉底。"""
    return sorted(
        tasks,
        key=lambda t: (t.is_done, t.due_at, PRIORITY_ORDER.get(t.priority, 0)),
    )


def due_snapshot(task: Task) -> tuple:
    return (format_dt(task.due_at), task.remind_due, task.status)
