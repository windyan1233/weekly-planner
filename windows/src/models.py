"""领域模型。

全部为纯 Python 数据类，不依赖 Qt，方便单元测试。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from .time_utils import covered_dates, format_dt, parse_dt, plan_range_label, remaining_label

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
KIND_PLAN_END = "plan_end"


def _row_value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    """从 sqlite3.Row / dict 里取一个可能不存在的新列（兼容旧库旧行）。"""
    try:
        keys = row.keys()
    except AttributeError:  # pragma: no cover - 防御性
        keys = ()
    return row[key] if key in keys else default


def _row_flag(row: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = _row_value(row, key, None)
    return default if value is None else bool(value)


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
    """任务下的一个计划时间（一个任务可以有 0..N 个）。

    开始时间 ``plan_at`` 必填；``end_at`` 可选（旧数据为空，表示不设置结束）。
    三个提醒开关相互独立：开始提醒（``remind_start``，提前 ``remind_lead_minutes``
    分钟）、结束提醒（``remind_end``，到结束时间时提醒）、截止提醒在 :class:`Task`
    的 ``remind_due`` 上。
    """

    id: int | None = None
    task_id: int | None = None
    plan_at: datetime = field(default_factory=datetime.now)
    label: str = ""
    remind_enabled: bool = False  # 旧字段：与 remind_start 保持同步
    remind_lead_minutes: int = 10
    done: bool = False
    sort_order: int = 0
    end_at: datetime | None = None
    remind_start: bool = True
    remind_end: bool = False

    # -- 提醒 -----------------------------------------------------------
    def reminder_at(self) -> datetime | None:
        """开始提醒时刻（沿用「提前 N 分钟」规则）。"""
        if not self.remind_start:
            return None
        return self.plan_at - timedelta(minutes=self.remind_lead_minutes)

    def end_reminder_at(self) -> datetime | None:
        """结束提醒时刻：正好是结束时间，不提前。"""
        if self.end_at is None or not self.remind_end:
            return None
        return self.end_at

    # -- 时间范围 -------------------------------------------------------
    @property
    def has_end(self) -> bool:
        return self.end_at is not None

    @property
    def is_cross_day(self) -> bool:
        return self.end_at is not None and self.end_at.date() != self.plan_at.date()

    @property
    def span_days(self) -> int:
        end = self.end_at or self.plan_at
        return max(1, (end.date() - self.plan_at.date()).days + 1)

    def covered_dates(self) -> list[date]:
        return covered_dates(self.plan_at, self.end_at)

    @property
    def range_text(self) -> str:
        """列表 / 描述里显示的时间文本。"""
        return plan_range_label(self.plan_at, self.end_at)

    @property
    def time_text(self) -> str:
        return self.plan_at.strftime("%H:%M")

    @property
    def date_text(self) -> str:
        return self.plan_at.strftime("%Y-%m-%d")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "PlanTime":
        # 旧库可能还没有 remind_start / remind_end / end_at 列（或旧行里为 NULL）：
        # 缺列时回退到旧的 remind_enabled，保证旧数据的提醒行为不变。
        legacy_start = _row_flag(row, "remind_enabled", False)
        start_enabled = _row_flag(row, "remind_start", legacy_start)
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            plan_at=parse_dt(row["plan_at"]) or datetime.now(),
            label=row["label"] or "",
            remind_enabled=start_enabled,
            remind_lead_minutes=int(row["remind_lead_minutes"]),
            done=bool(row["done"]),
            sort_order=int(row["sort_order"]),
            end_at=parse_dt(_row_value(row, "end_at")),
            remind_start=start_enabled,
            remind_end=_row_flag(row, "remind_end", False),
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
        parts = []
        for plan in self.sorted_plans():
            if plan.end_at is None:
                stamp = plan.plan_at.strftime("%m-%d %H:%M")
            elif plan.is_cross_day:
                stamp = plan.range_text
            else:
                stamp = f"{plan.plan_at.strftime('%m-%d')} {plan.range_text}"
            parts.append(f"{stamp} {plan.label}".strip())
        return "本任务共 {} 个计划时间：\n".format(len(parts)) + "\n".join(f"· {item}" for item in parts)

    def plan_covered_dates(self) -> list[date]:
        """计划时间覆盖到的日期（跨天计划会包含中间每一天）。"""
        days: list[date] = []
        for plan in self.sorted_plans():
            for day in plan.covered_dates():
                if day not in days:
                    days.append(day)
        return days

    def visible_dates(self) -> list[date]:
        """任务在周视图里可能出现的全部日期，截止日期排在最前。"""
        days = [self.due_at.date()]
        for day in self.plan_covered_dates():
            if day not in days:
                days.append(day)
        return days

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
    """周视图里的一个时间块：可能属于计划时间，也可能是截止时间。

    ``end_at`` 为计划时间的真实结束时间（旧计划为 ``None``，仍按固定时长显示）。
    跨天计划的结束时间可能落在后面的日期，周视图会按天裁剪成多段绘制。
    """

    task_id: int
    title: str
    kind: str
    start: datetime
    task: Task
    plan: PlanTime | None = None
    plan_index: int = 0
    plan_total: int = 0
    duration_minutes: int = 45
    end_at: datetime | None = None

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.kind, self.task_id, self.plan.id if self.plan else 0)

    @property
    def end(self) -> datetime:
        if self.end_at is not None:
            return self.end_at
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def is_cross_day(self) -> bool:
        return self.end_at is not None and self.end_at.date() != self.start.date()

    @property
    def span_days(self) -> int:
        return max(1, (self.end.date() - self.start.date()).days + 1)

    def covered_dates(self) -> list[date]:
        return covered_dates(self.start, self.end_at)

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
            bits = [f"计划 {plan_range_label(self.plan.plan_at, self.plan.end_at)}"]
            if self.plan.label:
                bits.append(self.plan.label)
            if self.plan.remind_start:
                bits.append(f"开始前 {self.plan.remind_lead_minutes} 分钟提醒")
            if self.plan.end_reminder_at() is not None:
                bits.append("结束提醒")
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
    remind_enabled: bool = False  # 旧字段：未显式给 remind_start 时作为开始提醒开关
    remind_lead_minutes: int = 10
    done: bool = False
    end_at: datetime | None = None
    # None 表示「调用方没指定」：回退到旧的 remind_enabled，保证旧代码的行为不变
    remind_start: bool | None = None
    remind_end: bool = False

    @property
    def start_reminder(self) -> bool:
        """开始提醒开关（新代码优先用 remind_start，旧代码仍可用 remind_enabled）。"""
        if self.remind_start is not None:
            return bool(self.remind_start)
        return bool(self.remind_enabled)


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
                    remind_enabled=plan.remind_start,
                    remind_start=plan.remind_start,
                    remind_lead_minutes=plan.remind_lead_minutes,
                    done=plan.done,
                    end_at=plan.end_at,
                    remind_end=plan.remind_end,
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
