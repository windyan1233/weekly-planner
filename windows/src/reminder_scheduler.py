"""提醒引擎与后台调度器。

* :class:`ReminderEngine` 只做纯逻辑 + SQL，不依赖 Qt，可直接单元测试。
* :class:`ReminderScheduler` 是常驻后台的 ``QObject``（跟随应用生命周期，
  不属于任何窗口）。窗口最小化到托盘、甚至主窗口从未打开，它都会照常工作。
* 除了 20 秒一次的轮询，还通过「单调时钟」判断电脑是否从睡眠恢复 / 系统时间
  是否被调整，并在发现跳变后重建全部提醒、立即补查。
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

import sqlite3

from PySide6.QtCore import QObject, QTimer, Signal

from . import config, repository
from .database import Database, DatabaseError
from .logging_setup import get_logger
from .models import (
    KIND_DUE,
    KIND_OVERDUE,
    KIND_PLAN,
    KIND_PLAN_END,
    PlanTime,
    Reminder,
    REMINDER_PENDING,
    REMINDER_SENT,
    REMINDER_SKIPPED,
    ReminderSpec,
    Task,
    priority_label,
)
from .settings_store import ReminderPolicy, SettingsStore
from .time_utils import (
    format_dt,
    humanize_delta,
    parse_dt,
    remaining_label,
)

logger = get_logger("reminder")


def compute_due_reminder(due_at: datetime, policy: ReminderPolicy) -> datetime:
    """按提醒策略计算截止提醒时刻。"""
    from .time_utils import due_reminder_time

    result = due_reminder_time(due_at, policy.mode, policy.previous_day_time)
    assert result is not None
    return result


@dataclass
class FiredReminder:
    """一条刚刚被判定为「应该通知」的提醒。"""

    reminder: Reminder
    task: Task
    plan: PlanTime | None = None
    late: timedelta = timedelta(0)
    overdue_notice: bool = False

    @property
    def kind(self) -> str:
        return self.reminder.kind


@dataclass
class ReminderMessage:
    """已排版好的通知内容（供通知管理器使用）。"""

    title: str
    body: str
    task_id: int
    reminder_id: int | None
    kind: str
    plan_id: int | None = None
    late_label: str = ""
    overdue: bool = False
    snooze_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "body": self.body,
            "task_id": self.task_id,
            "reminder_id": self.reminder_id,
            "kind": self.kind,
            "overdue": self.overdue,
        }


def _short_time(value: datetime) -> str:
    return value.strftime("%m月%d日 %H:%M")


def compose_message(fired: FiredReminder, now: datetime) -> ReminderMessage:
    task = fired.task
    late_seconds = int(fired.late.total_seconds())
    late_label = ""
    if late_seconds >= 120:
        late_label = "补发提醒 · 延迟 " + humanize_delta(timedelta(seconds=late_seconds))

    if fired.kind == KIND_PLAN:
        plan = fired.plan
        plan_at = plan.plan_at if plan else fired.reminder.fire_at
        detail = f"计划时间：{_short_time(plan_at)}"
        if plan and plan.end_at is not None:
            if plan.end_at.date() == plan.plan_at.date():
                detail += f" → {plan.end_at.strftime('%H:%M')}"
            else:
                detail += f" → {_short_time(plan.end_at)}"
        if plan and plan.label:
            detail += f" · {plan.label}"
        lines = [
            detail,
            f"截止时间：{_short_time(task.due_at)}",
            remaining_label(plan_at, now),
        ]
        if len(task.plans) > 1 and plan is not None:
            index, total = task.plan_index(plan.id)
            lines.append(f"本任务第 {index}/{total} 个计划时间")
        title = f"计划提醒 · {task.title}"
    elif fired.kind == KIND_PLAN_END:
        plan = fired.plan
        end_at = plan.end_at if plan and plan.end_at else fired.reminder.fire_at
        detail = f"计划结束：{_short_time(end_at)}"
        if plan and plan.label:
            detail += f" · {plan.label}"
        lines = [
            detail,
            f"截止时间：{_short_time(task.due_at)}",
            "计划已到结束时间" if end_at <= now else remaining_label(end_at, now),
        ]
        title = f"计划结束提醒 · {task.title}"
    elif fired.kind == KIND_OVERDUE:
        lines = [
            f"截止时间：{_short_time(task.due_at)}",
            remaining_label(task.due_at, now),
            f"{task.category} · {priority_label(task.priority)}",
        ]
        title = f"任务已逾期 · {task.title}"
    else:
        lines = [
            f"截止时间：{_short_time(task.due_at)}",
            remaining_label(task.due_at, now),
            f"{task.category} · {priority_label(task.priority)}",
        ]
        title = f"截止提醒 · {task.title}"

    if late_label:
        lines.append(f"（{late_label}）")
    if fired.reminder.snooze_count > 0 and not fired.overdue_notice:
        lines.append(f"（稍后提醒第 {fired.reminder.snooze_count} 次）")

    return ReminderMessage(
        title=title,
        body="\n".join(line for line in lines if line),
        task_id=int(task.id or 0),
        reminder_id=fired.reminder.id,
        kind=fired.kind,
        plan_id=fired.reminder.plan_id,
        late_label=late_label,
        overdue=fired.overdue_notice or fired.kind == KIND_OVERDUE,
        snooze_count=fired.reminder.snooze_count,
    )


class ReminderEngine:
    """提醒的持久化与判定逻辑。"""

    def __init__(self, db: Database, settings: SettingsStore) -> None:
        self._db = db
        self._settings = settings

    # ------------------------------------------------------------------
    # 推导 / 同步
    # ------------------------------------------------------------------
    def policy(self) -> ReminderPolicy:
        return self._settings.reminder_policy()

    def build_specs(self, task: Task) -> list[ReminderSpec]:
        if task.id is None or task.status == "done":
            return []
        specs: list[ReminderSpec] = []
        if task.remind_due:
            fire_at = compute_due_reminder(task.due_at, self.policy())
            specs.append(
                ReminderSpec(
                    task_id=int(task.id),
                    kind=KIND_DUE,
                    plan_id=None,
                    fire_at=fire_at,
                    anchor_at=format_dt(task.due_at),
                )
            )
        for plan in task.sorted_plans():
            if plan.done:
                continue
            if plan.remind_start:
                fire_at = plan.plan_at - timedelta(minutes=plan.remind_lead_minutes)
                specs.append(
                    ReminderSpec(
                        task_id=int(task.id),
                        kind=KIND_PLAN,
                        plan_id=plan.id,
                        fire_at=fire_at,
                        anchor_at=format_dt(plan.plan_at),
                    )
                )
            # 结束提醒：只有设置了结束时间且打开开关才生成，提醒时刻 = 结束时间（不提前）
            if plan.end_at is not None and plan.remind_end:
                specs.append(
                    ReminderSpec(
                        task_id=int(task.id),
                        kind=KIND_PLAN_END,
                        plan_id=plan.id,
                        fire_at=plan.end_at,
                        anchor_at=format_dt(plan.end_at),
                    )
                )
        return specs

    def sync_task(self, task: Task) -> dict[str, int]:
        """让数据库中的提醒与任务当前状态一致。"""
        if task.id is None:
            return {"created": 0, "removed": 0}
        task_id = int(task.id)
        specs = self.build_specs(task)
        spec_keys = {(spec.kind, spec.plan_id, spec.anchor_at) for spec in specs}
        existing = self._db.query(
            "SELECT * FROM reminders WHERE task_id = ? AND status IN (?, ?, ?)",
            (task_id, REMINDER_PENDING, REMINDER_SENT, REMINDER_SKIPPED),
        )
        removed = 0
        kept: dict[tuple[str, int | None, str], sqlite3.Row] = {}
        for row in existing:
            key = (row["kind"], row["plan_id"], row["anchor_at"])
            if key in spec_keys:
                kept[key] = row
                continue
            # 计划时间/截止时间变了，或提醒被关闭：只清理还没触发的；已触发的历史保留
            if row["status"] == REMINDER_PENDING:
                self._db.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))
                removed += 1
        created = 0
        updated = 0
        now_text = format_dt(datetime.now())
        for spec in specs:
            key = (spec.kind, spec.plan_id, spec.anchor_at)
            fire_text = format_dt(spec.fire_at)
            row = kept.get(key)
            if row is not None:
                # 提醒规则（例如「前 24 小时」改为「前一天 09:00」）变化后要更新触发时刻。
                # 已经被「稍后提醒」推迟的记录保持原时间，避免把用户的选择冲掉。
                if (
                    row["status"] == REMINDER_PENDING
                    and int(row["snooze_count"] or 0) == 0
                    and row["fire_at"] != fire_text
                ):
                    self._db.execute(
                        "UPDATE reminders SET fire_at = ? WHERE id = ?",
                        (fire_text, row["id"]),
                    )
                    updated += 1
                continue
            self._db.execute(
                "INSERT OR IGNORE INTO reminders(task_id, kind, plan_id, fire_at, status,"
                " fired_at, snooze_count, anchor_at, created_at) VALUES (?,?,?,?,?,NULL,0,?,?)",
                (
                    spec.task_id,
                    spec.kind,
                    spec.plan_id,
                    fire_text,
                    REMINDER_PENDING,
                    spec.anchor_at,
                    now_text,
                ),
            )
            created += 1
        if created or removed or updated:
            logger.debug(
                "同步任务 %s 的提醒：新增 %s，移除 %s，更新时间 %s",
                task_id,
                created,
                removed,
                updated,
            )
        return {"created": created, "removed": removed, "updated": updated}

    def sync_task_by_id(self, task_id: int) -> dict[str, int]:
        task = repository.fetch_task(self._db, task_id)
        if task is None:
            self._db.execute("DELETE FROM reminders WHERE task_id = ?", (task_id,))
            return {"created": 0, "removed": 0}
        return self.sync_task(task)

    def rebuild_all(self) -> dict[str, int]:
        """全量重建（启动、设置变更、系统时间跳变后调用）。"""
        tasks = repository.fetch_tasks(self._db, where="status != 'done'")
        created = removed = 0
        for task in tasks:
            stats = self.sync_task(task)
            created += stats["created"]
            removed += stats["removed"]
        # 清理孤立提醒（任务已删除的极端情况）
        self._db.execute(
            "DELETE FROM reminders WHERE task_id NOT IN (SELECT id FROM tasks)"
        )
        logger.info("重建提醒：新增 %s，移除 %s", created, removed)
        return {"created": created, "removed": removed}

    def cancel_pending(self, task_id: int) -> int:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM reminders WHERE task_id = ? AND status = ?",
                (task_id, REMINDER_PENDING),
            )
            return cursor.rowcount or 0

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def pending_reminders(self, now: datetime | None = None) -> list[Reminder]:
        rows = self._db.query(
            "SELECT * FROM reminders WHERE status = ? ORDER BY fire_at ASC",
            (REMINDER_PENDING,),
        )
        return [Reminder.from_row(row) for row in rows]

    def pending_count(self) -> int:
        return int(
            self._db.scalar(
                "SELECT COUNT(*) FROM reminders WHERE status = ?", (REMINDER_PENDING,)
            )
            or 0
        )

    def next_pending(self, now: datetime | None = None) -> tuple[Reminder, Task] | None:
        row = self._db.query_one(
            "SELECT * FROM reminders WHERE status = ? ORDER BY fire_at ASC LIMIT 1",
            (REMINDER_PENDING,),
        )
        if row is None:
            return None
        reminder = Reminder.from_row(row)
        task = repository.fetch_task(self._db, reminder.task_id)
        if task is None:
            return None
        return reminder, task

    def reminders_for_task(self, task_id: int, include_history: bool = True) -> list[Reminder]:
        if include_history:
            rows = self._db.query(
                "SELECT * FROM reminders WHERE task_id = ? ORDER BY fire_at ASC", (task_id,)
            )
        else:
            rows = self._db.query(
                "SELECT * FROM reminders WHERE task_id = ? AND status = ? ORDER BY fire_at ASC",
                (task_id, REMINDER_PENDING),
            )
        return [Reminder.from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # 触发判定
    # ------------------------------------------------------------------
    def _resolve(self, reminder: Reminder) -> tuple[Task | None, PlanTime | None]:
        task = repository.fetch_task(self._db, reminder.task_id)
        if task is None:
            return None, None
        plan = None
        if reminder.kind in (KIND_PLAN, KIND_PLAN_END):
            plan = next((p for p in task.plans if p.id == reminder.plan_id), None)
        return task, plan

    def _still_relevant(self, reminder: Reminder, task: Task, plan: PlanTime | None) -> bool:
        if task.status == "done":
            return False
        if reminder.kind == KIND_DUE:
            return task.remind_due and format_dt(task.due_at) == reminder.anchor_at
        if reminder.kind == KIND_PLAN:
            if plan is None or plan.done or not plan.remind_start:
                return False
            return format_dt(plan.plan_at) == reminder.anchor_at
        if reminder.kind == KIND_PLAN_END:
            if plan is None or plan.done or plan.end_at is None or not plan.remind_end:
                return False
            return format_dt(plan.end_at) == reminder.anchor_at
        if reminder.kind == KIND_OVERDUE:
            return task.is_overdue(reminder.fire_at)
        return True

    def claim_due(self, now: datetime | None = None) -> list[FiredReminder]:
        """取回所有到期提醒，并原子地标记为已发送 / 已跳过。"""
        now = now or datetime.now()
        rows = self._db.query(
            "SELECT * FROM reminders WHERE status = ? AND fire_at <= ? ORDER BY fire_at ASC",
            (REMINDER_PENDING, format_dt(now)),
        )
        grace = timedelta(hours=self.policy().grace_hours)
        fired: list[FiredReminder] = []
        for row in rows:
            reminder = Reminder.from_row(row)
            task, plan = self._resolve(reminder)
            if task is None or not self._still_relevant(reminder, task, plan):
                self._db.execute("DELETE FROM reminders WHERE id = ?", (reminder.id,))
                logger.debug("丢弃失效提醒 #%s", reminder.id)
                continue
            late = now - reminder.fire_at
            if late > grace:
                self._db.execute(
                    "UPDATE reminders SET status = ?, fired_at = ? WHERE id = ?",
                    (REMINDER_SKIPPED, format_dt(now), reminder.id),
                )
                logger.info(
                    "提醒 #%s 已错过（延迟 %s，超过补发窗口 %s 小时），标记为跳过",
                    reminder.id,
                    humanize_delta(late),
                    self.policy().grace_hours,
                )
                continue
            with self._db.transaction() as conn:
                conn.execute(
                    "UPDATE reminders SET status = ?, fired_at = ? WHERE id = ?",
                    (REMINDER_SENT, format_dt(now), reminder.id),
                )
                # 截止提醒本身已包含「已逾期」信息，避免再单独弹一条逾期通知
                if reminder.kind == KIND_DUE and task.is_overdue(now) and not task.overdue_notified:
                    conn.execute("UPDATE tasks SET overdue_notified = 1 WHERE id = ?", (task.id,))
                    task.overdue_notified = True
            reminder.status = REMINDER_SENT
            reminder.fired_at = now
            fired.append(FiredReminder(reminder=reminder, task=task, plan=plan, late=late))
        return fired

    def check_overdue(self, now: datetime | None = None) -> list[FiredReminder]:
        """找出「刚刚进入逾期状态」的任务，每个逾期状态只通知一次。

        逾期通知也会写入 reminders 表（kind='overdue'），这样「稍后提醒」按钮
        和重启后的去重都能复用同一套机制。
        """
        now = now or datetime.now()
        rows = self._db.query(
            "SELECT * FROM tasks WHERE status != 'done' AND due_at <= ? AND overdue_notified = 0"
            " ORDER BY due_at ASC",
            (format_dt(now),),
        )
        fired: list[FiredReminder] = []
        now_text = format_dt(now)
        for row in rows:
            task = Task.from_row(row)
            task_id = int(task.id or 0)
            with self._db.transaction() as conn:
                conn.execute("UPDATE tasks SET overdue_notified = 1 WHERE id = ?", (task_id,))
                # 对应的截止提醒不再重复发送
                conn.execute(
                    "DELETE FROM reminders WHERE task_id = ? AND kind = ? AND status = ?",
                    (task_id, KIND_DUE, REMINDER_PENDING),
                )
                existing = conn.execute(
                    "SELECT id FROM reminders WHERE task_id = ? AND kind = ? AND anchor_at = ?"
                    " AND status IN ('pending', 'sent')",
                    (task_id, KIND_OVERDUE, format_dt(task.due_at)),
                ).fetchone()
                if existing is None:
                    cursor = conn.execute(
                        "INSERT INTO reminders(task_id, kind, plan_id, fire_at, status, fired_at,"
                        " snooze_count, anchor_at, created_at) VALUES (?,?,NULL,?,?,?,0,?,?)",
                        (
                            task_id,
                            KIND_OVERDUE,
                            format_dt(task.due_at),
                            REMINDER_SENT,
                            now_text,
                            format_dt(task.due_at),
                            now_text,
                        ),
                    )
                    reminder_id = int(cursor.lastrowid or 0)
                    snooze_count = 0
                else:
                    reminder_id = int(existing["id"])
                    snooze_count = 0
            task.overdue_notified = True
            reminder = Reminder(
                id=reminder_id,
                task_id=task_id,
                kind=KIND_OVERDUE,
                fire_at=task.due_at,
                status=REMINDER_SENT,
                fired_at=now,
                snooze_count=snooze_count,
                anchor_at=format_dt(task.due_at),
            )
            logger.info("任务 #%s 已逾期：%s", task_id, task.title)
            fired.append(
                FiredReminder(
                    reminder=reminder,
                    task=task,
                    late=max(timedelta(0), now - task.due_at),
                    overdue_notice=True,
                )
            )
        return fired

    # ------------------------------------------------------------------
    # 稍后提醒
    # ------------------------------------------------------------------
    def snooze(self, reminder_id: int, minutes: int | None = None, now: datetime | None = None) -> datetime | None:
        now = now or datetime.now()
        minutes = minutes or self._settings.snooze_minutes()
        row = self._db.query_one("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        if row is None:
            return None
        reminder = Reminder.from_row(row)
        task = repository.fetch_task(self._db, reminder.task_id)
        if task is None or task.status == "done":
            return None
        target = now + timedelta(minutes=minutes)
        current_fire = parse_dt(row["fire_at"])
        if current_fire is not None and current_fire > target:
            # 原提醒本来就更晚，保持原时间
            target = current_fire
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE reminders SET fire_at = ?, status = ?, fired_at = NULL,"
                " snooze_count = snooze_count + 1 WHERE id = ?",
                (format_dt(target), REMINDER_PENDING, reminder_id),
            )
        logger.info("提醒 #%s 推迟到 %s", reminder_id, format_dt(target))
        return target

    def snooze_task_due(self, task_id: int, minutes: int | None = None, now: datetime | None = None) -> datetime | None:
        """通知按钮「稍后提醒」使用：找到该任务最近的一条提醒并推迟。"""
        row = self._db.query_one(
            "SELECT * FROM reminders WHERE task_id = ? ORDER BY fired_at DESC, id DESC LIMIT 1",
            (task_id,),
        )
        if row is None:
            return None
        return self.snooze(int(row["id"]), minutes, now)


class ReminderScheduler(QObject):
    """常驻后台的提醒调度器（QTimer + 睡眠/时钟跳变检测）。"""

    reminders_ready = Signal(object)     # list[ReminderMessage]
    resynchronized = Signal(str)         # 触发全量重建的原因
    next_reminder_changed = Signal(object)  # dict | None
    error_occurred = Signal(str)

    def __init__(
        self,
        engine: ReminderEngine,
        settings: SettingsStore,
        *,
        parent: QObject | None = None,
        clock: Callable[[], datetime] = datetime.now,
        monotonic: Callable[[], float] = _time.monotonic,
        interval_seconds: int = config.TICK_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._settings = settings
        self._clock = clock
        self._monotonic = monotonic
        self._interval = max(1, int(interval_seconds))
        self._last_now: datetime | None = None
        self._last_monotonic: float | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval * 1000)
        self._timer.setTimerType(config_qt_timer_type())
        self._timer.timeout.connect(self.tick)

    # ------------------------------------------------------------------
    @property
    def interval_seconds(self) -> int:
        return self._interval

    def start(self) -> None:
        self._timer.start()
        self.tick()
        logger.info("提醒调度器已启动，轮询间隔 %s 秒", self._interval)

    def stop(self) -> None:
        self._timer.stop()

    def is_active(self) -> bool:
        return self._timer.isActive()

    # ------------------------------------------------------------------
    def _detect_jump(self, now: datetime, mono: float) -> str:
        """返回跳变原因（空字符串表示正常）。"""
        if self._last_now is None or self._last_monotonic is None:
            return ""
        elapsed = mono - self._last_monotonic
        wall_delta = (now - self._last_now).total_seconds()
        if elapsed > self._interval * 3 + 120:
            return (
                "电脑可能刚从睡眠中恢复（程序挂起 "
                + humanize_delta(timedelta(seconds=int(elapsed)))
                + "）"
            )
        if abs(wall_delta - elapsed) > 90:
            return (
                "检测到系统时间变化（墙上时间变化 "
                + humanize_delta(timedelta(seconds=abs(int(wall_delta))))
                + "）"
            )
        return ""

    def tick(self, now: datetime | None = None, monotonic: float | None = None) -> list[ReminderMessage]:
        """执行一次检查。可注入时间，便于测试。"""
        current = now or self._clock()
        mono = self._monotonic() if monotonic is None else monotonic
        messages: list[ReminderMessage] = []
        try:
            reason = self._detect_jump(current, mono)
            if reason:
                logger.info("检测到时间跳变：%s，重建提醒", reason)
                self._engine.rebuild_all()
                self.resynchronized.emit(reason)
            for fired in self._engine.check_overdue(current):
                messages.append(compose_message(fired, current))
            for fired in self._engine.claim_due(current):
                messages.append(compose_message(fired, current))
        except DatabaseError as exc:
            logger.exception("提醒检查时数据库出错")
            self.error_occurred.emit(exc.user_message())
        except Exception as exc:  # pragma: no cover - 最后一道防线
            logger.exception("提醒检查出现未预期错误")
            self.error_occurred.emit(f"提醒检查失败：{exc}")
        finally:
            self._last_now = current
            self._last_monotonic = mono
            self._emit_next()

        if messages:
            self.reminders_ready.emit(messages)
        return messages

    def _emit_next(self) -> None:
        try:
            item = self._engine.next_pending()
        except DatabaseError:
            return
        if item is None:
            self.next_reminder_changed.emit(None)
            return
        reminder, task = item
        self.next_reminder_changed.emit(
            {
                "fire_at": reminder.fire_at,
                "title": task.title,
                "kind": reminder.kind,
            }
        )


def config_qt_timer_type():
    """提醒计时器使用粗粒度类型，省电且足够精确。"""
    from PySide6.QtCore import Qt

    return Qt.TimerType.CoarseTimer
