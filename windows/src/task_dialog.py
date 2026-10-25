"""任务创建 / 编辑 / 详情窗口。

任务可以拥有任意多个计划时间，每个计划时间都可以独立设置开始前提醒；
截止时间与计划时间分开保存，互不覆盖。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .database import DatabaseError
from .models import (
    PRIORITIES,
    STATUSES,
    PlanDraft,
    PlanTime,
    Task,
    TaskDraft,
    priority_label,
    status_label,
)
from .task_manager import PlannerService, ValidationError
from .time_utils import REMINDER_MODE_LABELS, humanize_delta, remaining_label
from .widgets import Card, section_title

LEAD_OPTIONS: tuple[tuple[int, str], ...] = (
    (0, "不提醒"),
    (5, "提前 5 分钟"),
    (10, "提前 10 分钟"),
    (15, "提前 15 分钟"),
    (30, "提前 30 分钟"),
    (60, "提前 1 小时"),
)


def _lead_index(minutes: int) -> int:
    options = [value for value, _ in LEAD_OPTIONS]
    if minutes in options:
        return options.index(minutes)
    return options.index(10)


def _date_of(value: datetime) -> QDate:
    return QDate(value.year, value.month, value.day)


def _time_of(value: datetime) -> QTime:
    return QTime(value.hour, value.minute)


def _datetime(date_edit: QDateEdit, time_edit: QTimeEdit) -> datetime:
    d = date_edit.date()
    t = time_edit.time()
    return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Subtitle")
    label.setWordWrap(True)
    return label


class PlanRow(QFrame):
    """对话框里的一行计划时间。"""

    removed = Signal(object)

    def __init__(self, draft: PlanDraft, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SoftCard")
        self._plan_id = draft.id
        self._done = draft.done
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(6)

        self.date_edit = QDateEdit(_date_of(draft.plan_at))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFixedWidth(128)
        layout.addWidget(self.date_edit)

        self.time_edit = QTimeEdit(_time_of(draft.plan_at))
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFixedWidth(76)
        layout.addWidget(self.time_edit)

        self.label_edit = QLineEdit(draft.label)
        self.label_edit.setPlaceholderText("这一步做什么（选填）")
        layout.addWidget(self.label_edit, 1)

        self.remind_combo = QComboBox()
        for minutes, text in LEAD_OPTIONS:
            prefix = "" if minutes == 0 else "开始前 "
            self.remind_combo.addItem(text if minutes == 0 else f"{prefix}{text}", minutes)
        self.remind_combo.setCurrentIndex(
            _lead_index(draft.remind_lead_minutes) if draft.remind_enabled else 0
        )
        self.remind_combo.setFixedWidth(128)
        self.remind_combo.setToolTip("为这个计划时间单独设置开始前提醒")
        layout.addWidget(self.remind_combo)

        if draft.done:
            done_label = QLabel("已完成")
            done_label.setObjectName("Subtitle")
            layout.addWidget(done_label)

        remove_button = QPushButton("×")
        remove_button.setObjectName("Ghost")
        remove_button.setFixedSize(26, 26)
        remove_button.setToolTip("移除这个计划时间（不会删除任务）")
        remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_button.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(remove_button)

    @property
    def plan_id(self) -> int | None:
        return self._plan_id

    def focus_first(self) -> None:
        self.date_edit.setFocus()

    def to_draft(self) -> PlanDraft:
        minutes = int(self.remind_combo.currentData() or 0)
        return PlanDraft(
            id=self._plan_id,
            plan_at=_datetime(self.date_edit, self.time_edit),
            label=self.label_edit.text().strip(),
            remind_enabled=minutes > 0,
            remind_lead_minutes=minutes if minutes > 0 else 10,
            done=self._done,
        )


class TaskDialog(QDialog):
    """新建 / 编辑任务。"""

    task_saved = Signal(int)

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None,
        *,
        task: Task | None = None,
        initial_due: datetime | None = None,
        initial_plan: datetime | None = None,
        initial_date: date | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._task = task
        self._saved_task_id: int | None = None
        self._plan_rows: list[PlanRow] = []
        self._categories = service.categories()

        self.setWindowTitle("编辑任务" if task else "新建任务")
        self.setModal(True)
        self.setMinimumWidth(760)

        due_default = task.due_at if task else self._default_due(initial_due, initial_plan, initial_date)
        plan_default = initial_plan

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("编辑任务" if task else "新建任务")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addWidget(_hint("计划时间可以添加多个；截止时间与计划时间分别保存。"))
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(2, 2, 8, 2)
        form.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # -- 基本信息 ------------------------------------------------------
        form.addWidget(section_title("任务名称"))
        self.title_edit = QLineEdit(task.title if task else "")
        self.title_edit.setPlaceholderText("例如：完成课程报告")
        self.title_edit.setMaxLength(120)
        form.addWidget(self.title_edit)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        category_box = QVBoxLayout()
        category_box.setSpacing(4)
        category_box.addWidget(_muted("分类"))
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(self._categories)
        self.category_combo.setCurrentText(task.category if task else self._categories[0])
        self.category_combo.setMinimumWidth(150)
        self.category_combo.lineEdit().setPlaceholderText("可直接输入新分类")
        category_box.addWidget(self.category_combo)
        meta_row.addLayout(category_box, 2)

        status_box = QVBoxLayout()
        status_box.setSpacing(4)
        status_box.addWidget(_muted("状态"))
        self.status_combo = QComboBox()
        for key, label in STATUSES:
            self.status_combo.addItem(label, key)
        self.status_combo.setCurrentIndex(
            [key for key, _ in STATUSES].index(task.status) if task and task.status in dict(STATUSES) else 0
        )
        status_box.addWidget(self.status_combo)
        meta_row.addLayout(status_box, 1)

        priority_box = QVBoxLayout()
        priority_box.setSpacing(4)
        priority_box.addWidget(_muted("优先级"))
        priority_row = QHBoxLayout()
        priority_row.setSpacing(6)
        self.priority_group = QButtonGroup(self)
        current_priority = task.priority if task else "normal"
        for key, label in PRIORITIES:
            button = QPushButton(label)
            button.setObjectName("Segmented")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("priority", key)
            button.setChecked(key == current_priority)
            self.priority_group.addButton(button)
            priority_row.addWidget(button)
        priority_box.addLayout(priority_row)
        meta_row.addLayout(priority_box, 2)
        form.addLayout(meta_row)

        # -- 截止时间 ------------------------------------------------------
        form.addWidget(section_title("截止时间（最晚必须完成的时间）"))
        due_row = QHBoxLayout()
        due_row.setSpacing(8)
        self.due_date_edit = QDateEdit(_date_of(due_default))
        self.due_date_edit.setCalendarPopup(True)
        self.due_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.due_date_edit.setFixedWidth(136)
        due_row.addWidget(self.due_date_edit)
        self.due_time_edit = QTimeEdit(_time_of(due_default))
        self.due_time_edit.setDisplayFormat("HH:mm")
        self.due_time_edit.setFixedWidth(80)
        due_row.addWidget(self.due_time_edit)
        self.remind_checkbox = QPushButton("截止前一天提醒")
        self.remind_checkbox.setObjectName("Segmented")
        self.remind_checkbox.setCheckable(True)
        self.remind_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remind_checkbox.setChecked(task.remind_due if task else True)
        self.remind_checkbox.setToolTip("默认在截止时间前 24 小时提醒一次，可在设置中改为前一天指定时间")
        due_row.addWidget(self.remind_checkbox)
        due_row.addStretch(1)
        form.addLayout(due_row)

        self.reminder_preview = QLabel()
        self.reminder_preview.setObjectName("Subtitle")
        self.reminder_preview.setWordWrap(True)
        form.addWidget(self.reminder_preview)

        # -- 计划时间 ------------------------------------------------------
        plan_header = QHBoxLayout()
        plan_header.addWidget(section_title("计划时间（打算什么时候做，可添加多个）"))
        plan_header.addStretch(1)
        self.add_plan_button = QPushButton("＋ 添加计划时间")
        self.add_plan_button.setObjectName("Ghost")
        self.add_plan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_plan_button.clicked.connect(self._add_plan_row)
        plan_header.addWidget(self.add_plan_button)
        form.addLayout(plan_header)

        self.plan_container = QVBoxLayout()
        self.plan_container.setSpacing(6)
        form.addLayout(self.plan_container)

        self.plan_empty_hint = _hint("还没有计划时间。添加后，它会出现在对应日期的周视图里。")
        form.addWidget(self.plan_empty_hint)

        self.plan_total_label = _muted("")
        form.addWidget(self.plan_total_label)

        for plan in (task.sorted_plans() if task else []):
            self._add_plan_row(
                PlanDraft(
                    id=plan.id,
                    plan_at=plan.plan_at,
                    label=plan.label,
                    remind_enabled=plan.remind_enabled,
                    remind_lead_minutes=plan.remind_lead_minutes,
                    done=plan.done,
                )
            )
        if not task and initial_plan:
            self._add_plan_row(PlanDraft(plan_at=initial_plan))

        # -- 说明 / 备注 ---------------------------------------------------
        form.addWidget(section_title("任务说明（选填）"))
        self.description_edit = QPlainTextEdit(task.description if task else "")
        self.description_edit.setPlaceholderText("补充背景、要求、链接等")
        self.description_edit.setFixedHeight(76)
        form.addWidget(self.description_edit)

        form.addWidget(section_title("备注（选填）"))
        self.notes_edit = QPlainTextEdit(task.notes if task else "")
        self.notes_edit.setPlaceholderText("给自己留一句话")
        self.notes_edit.setFixedHeight(60)
        form.addWidget(self.notes_edit)
        form.addStretch(1)

        # -- 底部按钮 ------------------------------------------------------
        self.error_label = QLabel()
        self.error_label.setObjectName("ErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        if task:
            self.delete_button = QPushButton("删除任务")
            self.delete_button.setObjectName("Danger")
            self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.delete_button.clicked.connect(self._delete_task)
            footer.addWidget(self.delete_button)
            self.duplicate_button = QPushButton("复制任务")
            self.duplicate_button.setObjectName("Ghost")
            self.duplicate_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.duplicate_button.clicked.connect(self._duplicate_task)
            footer.addWidget(self.duplicate_button)
        footer.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("Primary")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        footer.addWidget(self.save_button)
        root.addLayout(footer)

        self.due_date_edit.dateChanged.connect(lambda *_: self._update_reminder_preview())
        self.due_time_edit.timeChanged.connect(lambda *_: self._update_reminder_preview())
        self.remind_checkbox.toggled.connect(lambda *_: self._update_reminder_preview())
        self._update_reminder_preview()
        self._update_plan_count()

        self.title_edit.setFocus()
        self.resize(780, 760)

    # ------------------------------------------------------------------
    # 默认值
    # ------------------------------------------------------------------
    def _default_due(
        self,
        initial_due: datetime | None,
        initial_plan: datetime | None,
        initial_date: date | None,
    ) -> datetime:
        if initial_due is not None:
            return initial_due
        if initial_plan is not None:
            return initial_plan + timedelta(hours=3)
        if initial_date is not None:
            return datetime.combine(initial_date, time(18, 0))
        now = datetime.now().replace(second=0, microsecond=0)
        base = now.replace(hour=18, minute=0)
        if base <= now:
            base += timedelta(days=1)
        return base

    # ------------------------------------------------------------------
    # 计划时间行
    # ------------------------------------------------------------------
    def _next_plan_default(self) -> datetime:
        if self._plan_rows:
            last = self._plan_rows[-1].to_draft().plan_at
            candidate = last + timedelta(hours=1)
            if candidate.hour >= 23:
                candidate = last.replace(hour=19, minute=0) + timedelta(days=1)
            return candidate
        due = _datetime(self.due_date_edit, self.due_time_edit)
        base = due.replace(hour=19, minute=0)
        if base > due:
            base = due - timedelta(hours=2)
            base = base.replace(minute=0)
        return base

    def _add_plan_row(self, draft: PlanDraft | None = None) -> None:
        draft = draft or PlanDraft(plan_at=self._next_plan_default())
        row = PlanRow(draft, self)
        row.removed.connect(self._remove_plan_row)
        self.plan_container.addWidget(row)
        self._plan_rows.append(row)
        self.plan_empty_hint.hide()
        self._update_plan_count()
        row.focus_first()

    def _remove_plan_row(self, row: PlanRow) -> None:
        if row in self._plan_rows:
            self._plan_rows.remove(row)
            row.setParent(None)
            row.deleteLater()
        self._update_plan_count()

    def _update_plan_count(self) -> None:
        count = len(self._plan_rows)
        self.plan_empty_hint.setVisible(count == 0)
        self.plan_total_label.setText(
            f"共 {count} 个计划时间" if count else ""
        )

    # ------------------------------------------------------------------
    def _update_reminder_preview(self) -> None:
        due = _datetime(self.due_date_edit, self.due_time_edit)
        if not self.remind_checkbox.isChecked():
            self.reminder_preview.setText("已关闭这条任务的截止提醒（计划时间提醒仍然有效）。")
            return
        policy = self._service.settings.reminder_policy()
        from .reminder_scheduler import compute_due_reminder

        fire_at = compute_due_reminder(due, policy)
        rule = REMINDER_MODE_LABELS.get(policy.mode, "")
        if fire_at <= datetime.now():
            self.reminder_preview.setText(
                f"提醒时间 {fire_at.strftime('%m月%d日 %H:%M')} 已经过去，不会补发。"
                f"（当前规则：{rule}，可在设置中修改）"
            )
            self.reminder_preview.setStyleSheet("")
        else:
            self.reminder_preview.setText(
                f"将于 {fire_at.strftime('%m月%d日 %H:%M')} 提醒（{rule}），"
                f"还有 {humanize_delta(fire_at - datetime.now())}。"
            )

    # ------------------------------------------------------------------
    def _selected_priority(self) -> str:
        for button in self.priority_group.buttons():
            if button.isChecked():
                return str(button.property("priority") or "normal")
        return "normal"

    def _build_draft(self) -> TaskDraft:
        draft = TaskDraft(
            title=self.title_edit.text().strip(),
            description=self.description_edit.toPlainText().strip(),
            due_at=_datetime(self.due_date_edit, self.due_time_edit),
            category=self.category_combo.currentText().strip() or "学习",
            priority=self._selected_priority(),
            status=str(self.status_combo.currentData() or "todo"),
            remind_due=self.remind_checkbox.isChecked(),
            notes=self.notes_edit.toPlainText().strip(),
            plans=[row.to_draft() for row in self._plan_rows],
        )
        return draft

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.show()

    def _save(self) -> None:
        draft = self._build_draft()
        if not draft.title:
            self._show_error("请填写任务名称。")
            self.title_edit.setFocus()
            return
        category = draft.category
        if category not in self._categories:
            self._service.settings.add_category(category)
            self._categories = self._service.categories()
            current = self.category_combo.currentText()
            self.category_combo.clear()
            self.category_combo.addItems(self._categories)
            self.category_combo.setCurrentText(current)
        try:
            if self._task is None:
                task = self._service.create_task(draft)
            else:
                task = self._service.update_task(int(self._task.id or 0), draft)
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except DatabaseError as exc:
            self.error_label.setText(exc.user_message())
            self.error_label.show()
            QMessageBox.critical(self, "保存失败", exc.user_message())
            return
        self._saved_task_id = int(task.id or 0)
        self.task_saved.emit(self._saved_task_id)
        self.accept()

    # ------------------------------------------------------------------
    def _delete_task(self) -> None:
        if self._task is None:
            return
        answer = QMessageBox.question(
            self,
            "删除任务",
            f"确定要删除「{self._task.title}」吗？\n该任务的所有计划时间与待触发提醒都会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_task(int(self._task.id or 0))
        except DatabaseError as exc:
            QMessageBox.critical(self, "删除失败", exc.user_message())
            return
        self._saved_task_id = None
        self.setProperty("deleted", True)
        self.done(QDialog.DialogCode.Accepted)

    def _duplicate_task(self) -> None:
        draft = self._build_draft()
        if not draft.title:
            self._show_error("请填写任务名称。")
            return
        draft.title = f"{draft.title}（副本）"
        draft.status = "todo"
        draft.plans = [
            PlanDraft(
                plan_at=plan.plan_at,
                label=plan.label,
                remind_enabled=plan.remind_enabled,
                remind_lead_minutes=plan.remind_lead_minutes,
            )
            for plan in draft.plans
        ]
        try:
            task = self._service.create_task(draft)
        except (ValidationError, DatabaseError) as exc:
            message = exc.user_message() if isinstance(exc, DatabaseError) else str(exc)
            self._show_error(message)
            return
        self._saved_task_id = int(task.id or 0)
        self.task_saved.emit(self._saved_task_id)
        self.accept()

    # ------------------------------------------------------------------
    @property
    def saved_task_id(self) -> int | None:
        return self._saved_task_id

    @property
    def was_deleted(self) -> bool:
        return bool(self.property("deleted"))


class PlanEditDialog(QDialog):
    """单独编辑某一个计划时间。"""

    def __init__(self, service: PlannerService, plan: PlanTime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._plan = plan
        self.setWindowTitle("编辑计划时间")
        self.setModal(True)
        self.setFixedWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel(plan.label or "计划时间")
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_hint("只修改这一个计划时间，不会影响任务的其它计划时间或截止时间。"))

        row = QHBoxLayout()
        row.setSpacing(8)
        self.date_edit = QDateEdit(_date_of(plan.plan_at))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        row.addWidget(self.date_edit)
        self.time_edit = QTimeEdit(_time_of(plan.plan_at))
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFixedWidth(80)
        row.addWidget(self.time_edit)
        layout.addLayout(row)

        self.label_edit = QLineEdit(plan.label)
        self.label_edit.setPlaceholderText("这一步做什么（选填）")
        layout.addWidget(self.label_edit)

        self.remind_combo = QComboBox()
        for minutes, text in LEAD_OPTIONS:
            self.remind_combo.addItem(text if minutes == 0 else f"开始前 {text}", minutes)
        self.remind_combo.setCurrentIndex(
            _lead_index(plan.remind_lead_minutes) if plan.remind_enabled else 0
        )
        layout.addWidget(self.remind_combo)

        self.done_checkbox = QPushButton("这一步已完成")
        self.done_checkbox.setObjectName("Segmented")
        self.done_checkbox.setCheckable(True)
        self.done_checkbox.setChecked(plan.done)
        layout.addWidget(self.done_checkbox)

        error = QLabel()
        error.setObjectName("ErrorLabel")
        error.hide()
        self._error = error
        layout.addWidget(error)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        footer.addWidget(save)
        layout.addLayout(footer)

    def _save(self) -> None:
        minutes = int(self.remind_combo.currentData() or 0)
        try:
            self._service.update_plan(
                int(self._plan.id or 0),
                plan_at=_datetime(self.date_edit, self.time_edit),
                label=self.label_edit.text(),
                remind_enabled=minutes > 0,
                remind_lead_minutes=minutes if minutes > 0 else self._plan.remind_lead_minutes,
                done=self.done_checkbox.isChecked(),
            )
        except DatabaseError as exc:
            self._error.setText(exc.user_message())
            self._error.show()
            return
        self.accept()


class TaskDetailDialog(QDialog):
    """查看完整详情，并可直接完成 / 编辑 / 删除 / 管理单个计划时间。"""

    changed = Signal()

    def __init__(self, service: PlannerService, task_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._task_id = task_id
        self.setWindowTitle("任务详情")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.resize(600, 640)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(22, 20, 22, 16)
        self._root.setSpacing(12)
        self._rebuild()

    # ------------------------------------------------------------------
    def _clear(self) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _task(self) -> Task:
        return self._service.get_task(self._task_id)

    def _rebuild(self) -> None:
        self._clear()
        task = self._task()
        now = datetime.now()

        title = QLabel(task.title)
        title.setObjectName("Title")
        title.setWordWrap(True)
        self._root.addWidget(title)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        badges.addWidget(self._pill(status_label(task.status), "status"))
        badges.addWidget(self._pill(priority_label(task.priority), "priority"))
        badges.addWidget(self._pill(task.category, "category"))
        if task.is_overdue(now):
            badges.addWidget(self._pill("已逾期 " + remaining_label(task.due_at, now).replace("已逾期 ", ""), "danger"))
        badges.addStretch(1)
        self._root.addLayout(badges)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(12)
        scroll.setWidget(body)
        self._root.addWidget(scroll, 1)

        # 截止信息
        due_card = Card(soft=True)
        due_layout = QVBoxLayout(due_card)
        due_layout.setContentsMargins(14, 12, 14, 12)
        due_layout.setSpacing(4)
        due_layout.addWidget(section_title("截止时间"))
        due_label = QLabel(f"{task.due_at.strftime('%Y 年 %m 月 %d 日 %H:%M')}")
        due_font = QFont(due_label.font())
        due_font.setPixelSize(17)
        due_font.setWeight(QFont.Weight.DemiBold)
        due_label.setFont(due_font)
        due_layout.addWidget(due_label)
        if task.is_done:
            due_layout.addWidget(_muted("任务已完成，未触发的提醒已取消。"))
        else:
            due_layout.addWidget(_muted(remaining_label(task.due_at, now)))
        reminder_at = self._service.preview_due_reminder(task)
        if not task.remind_due:
            due_layout.addWidget(_muted("截止提醒：已关闭"))
        elif reminder_at is not None:
            sent = self._reminder_state(task)
            due_layout.addWidget(
                _muted(f"截止提醒：{reminder_at.strftime('%m月%d日 %H:%M')}{sent}")
            )
        content.addWidget(due_card)

        # 计划时间
        content.addWidget(section_title(f"计划时间（{len(task.plans)} 个）"))
        if not task.plans:
            content.addWidget(_hint("这个任务还没有计划时间。"))
        for index, plan in enumerate(task.sorted_plans(), start=1):
            content.addWidget(self._plan_card(task, plan, index, now))

        # 说明 / 备注
        if task.description:
            content.addWidget(section_title("任务说明"))
            description = QLabel(task.description)
            description.setWordWrap(True)
            description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            content.addWidget(description)
        if task.notes:
            content.addWidget(section_title("备注"))
            notes = QLabel(task.notes)
            notes.setWordWrap(True)
            notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            content.addWidget(notes)

        # 提醒记录
        reminders = self._service.engine.reminders_for_task(task.id) if self._service.engine else []
        history = [r for r in reminders if r.status in ("sent", "skipped")]
        if history:
            content.addWidget(section_title("提醒记录"))
            for reminder in history[-4:]:
                kind = {"due": "截止提醒", "plan": "计划提醒", "overdue": "逾期提醒"}.get(
                    reminder.kind, reminder.kind
                )
                state = "已发送" if reminder.status == "sent" else "已错过（超过补发窗口）"
                when = reminder.fired_at.strftime("%m-%d %H:%M") if reminder.fired_at else "—"
                content.addWidget(_muted(f"{kind} · 计划于 {reminder.fire_at.strftime('%m-%d %H:%M')} · {state} {when}"))
        content.addStretch(1)

        # 底部按钮
        footer = QHBoxLayout()
        footer.setSpacing(8)
        toggle = QPushButton("重新打开" if task.is_done else "标记完成")
        toggle.setObjectName("Primary" if not task.is_done else "")
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.clicked.connect(self._toggle_done)
        footer.addWidget(toggle)

        edit = QPushButton("编辑任务")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(self._edit)
        footer.addWidget(edit)

        duplicate = QPushButton("复制")
        duplicate.setObjectName("Ghost")
        duplicate.setCursor(Qt.CursorShape.PointingHandCursor)
        duplicate.clicked.connect(self._duplicate)
        footer.addWidget(duplicate)

        delete = QPushButton("删除")
        delete.setObjectName("Danger")
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.clicked.connect(self._delete)
        footer.addWidget(delete)

        footer.addStretch(1)
        close = QPushButton("关闭")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        self._root.addLayout(footer)

    # ------------------------------------------------------------------
    def _reminder_state(self, task: Task) -> str:
        if not self._service.engine or task.id is None:
            return ""
        now = datetime.now()
        rows = self._service.engine.reminders_for_task(task.id, include_history=True)
        due_rows = [r for r in rows if r.kind == "due"]
        pending = [r for r in due_rows if r.status == "pending"]
        if pending:
            return "（等待发送）" if pending[0].fire_at > now else "（已过提醒时间）"
        if any(r.status == "sent" for r in due_rows):
            return "（已发送）"
        if any(r.status == "skipped" for r in due_rows):
            return "（已错过）"
        return ""

    def _pill(self, text: str, kind: str) -> QLabel:
        from .theme import current_palette

        palette = current_palette()
        colors = {
            "status": (palette.accent, palette.accent_soft),
            "priority": (palette.warning, palette.warning_soft),
            "category": (palette.success, palette.success_soft),
            "danger": (palette.danger, palette.danger_soft),
        }
        fg, bg = colors.get(kind, (palette.text_secondary, palette.surface_alt))
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border-radius: 9px; padding: 2px 9px; font-size: 11px;"
        )
        return label

    def _plan_card(self, task: Task, plan: PlanTime, index: int, now: datetime) -> QWidget:
        card = Card(soft=True)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)

        check = QCheckBox()
        check.setChecked(plan.done)
        check.setFixedSize(20, 20)
        check.setToolTip("标记这一个计划时间完成" if not plan.done else "取消完成")
        check.setCursor(Qt.CursorShape.PointingHandCursor)
        check.toggled.connect(lambda checked, p=plan: self._set_plan_done(p, checked))
        layout.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)

        column = QVBoxLayout()
        column.setSpacing(2)
        time_label = QLabel(f"{plan.plan_at.strftime('%m 月 %d 日 %H:%M')}")
        font = QFont(time_label.font())
        font.setWeight(QFont.Weight.DemiBold)
        time_label.setFont(font)
        if plan.done:
            font.setStrikeOut(True)
            time_label.setFont(font)
        column.addWidget(time_label)
        detail = [f"第 {index} 个计划时间"]
        if plan.label:
            detail.append(plan.label)
        if plan.done:
            detail.append("已完成")
        elif plan.remind_enabled:
            detail.append(f"开始前 {plan.remind_lead_minutes} 分钟提醒")
        else:
            detail.append("无提醒")
        if task.is_overdue(now) and not task.is_done:
            detail.append("任务已逾期")
        column.addWidget(_muted(" · ".join(detail)))
        layout.addLayout(column, 1)

        edit = QPushButton("编辑")
        edit.setObjectName("Ghost")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(lambda _=False, p=plan: self._edit_plan(p))
        layout.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)

        delete = QPushButton("删除")
        delete.setObjectName("Ghost")
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.setToolTip("只删除这个计划时间")
        delete.clicked.connect(lambda _=False, p=plan: self._delete_plan(p))
        layout.addWidget(delete, 0, Qt.AlignmentFlag.AlignTop)
        return card

    # ------------------------------------------------------------------
    def _after_change(self) -> None:
        self.changed.emit()
        self._rebuild()

    def _toggle_done(self) -> None:
        try:
            self._service.toggle_done(self._task_id)
        except DatabaseError as exc:
            QMessageBox.critical(self, "操作失败", exc.user_message())
            return
        self._after_change()

    def _set_plan_done(self, plan: PlanTime, done: bool) -> None:
        try:
            self._service.set_plan_done(int(plan.id or 0), done)
        except DatabaseError as exc:
            QMessageBox.critical(self, "操作失败", exc.user_message())
            return
        self._after_change()

    def _toggle_plan(self, plan: PlanTime) -> None:
        self._set_plan_done(plan, not plan.done)

    def _edit_plan(self, plan: PlanTime) -> None:
        dialog = PlanEditDialog(self._service, plan, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._after_change()

    def _delete_plan(self, plan: PlanTime) -> None:
        answer = QMessageBox.question(
            self,
            "删除计划时间",
            f"确定删除 {plan.plan_at.strftime('%m月%d日 %H:%M')} 这个计划时间吗？\n任务本身和其它计划时间不会受影响。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_plan(int(plan.id or 0))
        except DatabaseError as exc:
            QMessageBox.critical(self, "删除失败", exc.user_message())
            return
        self._after_change()

    def _edit(self) -> None:
        task = self._task()
        dialog = TaskDialog(self._service, self, task=task)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._after_change()

    def _duplicate(self) -> None:
        try:
            task = self._service.duplicate_task(self._task_id)
        except DatabaseError as exc:
            QMessageBox.critical(self, "复制失败", exc.user_message())
            return
        self._task_id = int(task.id or 0)
        self._after_change()

    def _delete(self) -> None:
        task = self._task()
        answer = QMessageBox.question(
            self,
            "删除任务",
            f"确定要删除「{task.title}」吗？\n相关计划时间和待触发提醒会一并删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_task(self._task_id)
        except DatabaseError as exc:
            QMessageBox.critical(self, "删除失败", exc.user_message())
            return
        self.changed.emit()
        self.accept()
