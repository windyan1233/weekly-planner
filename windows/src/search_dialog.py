"""跨周搜索窗口：按任务名称（也匹配说明、备注、分类）查找全部任务。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .models import Task, priority_label, status_label
from .task_manager import PlannerService
from .time_utils import remaining_label, start_of_week, week_days


class SearchDialog(QDialog):
    task_activated = Signal(int)

    def __init__(
        self,
        service: PlannerService,
        parent: QWidget | None = None,
        *,
        initial_text: str = "",
        current_week: datetime | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._current_week = current_week or datetime.now()
        self._tasks: list[Task] = []
        self.setWindowTitle("搜索任务")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.resize(620, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("搜索任务")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.search_edit = QLineEdit(initial_text)
        self.search_edit.setPlaceholderText("输入任务名称、说明、备注或分类")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh)
        layout.addWidget(self.search_edit)

        self.hint = QLabel("")
        self.hint.setObjectName("Subtitle")
        layout.addWidget(self.hint)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(0, 0))
        self.list_widget.itemDoubleClicked.connect(self._open_item)
        self.list_widget.itemActivated.connect(self._open_item)
        layout.addWidget(self.list_widget, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        self.open_button = QPushButton("查看任务")
        self.open_button.setObjectName("Primary")
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self._open_selected)
        footer.addWidget(self.open_button)
        layout.addLayout(footer)

        self._refresh()

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        needle = self.search_edit.text().strip()
        self.list_widget.clear()
        self._tasks = self._service.search_tasks(needle) if needle else []
        if not needle:
            self.hint.setText("输入关键字开始搜索（会搜索全部日期，而不只是当前这一周）")
            return
        if not self._tasks:
            self.hint.setText("没有找到匹配的任务。")
            return
        week = set(week_days(start_of_week(self._current_week)))
        outside = 0
        now = datetime.now()
        for task in self._tasks:
            due_date = task.due_at.date()
            in_week = due_date in week or any(plan.plan_at.date() in week for plan in task.plans)
            if not in_week:
                outside += 1
            text = self._describe(task, in_week, now)
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, int(task.id or 0))
            item.setToolTip(task.description or task.notes or task.title)
            self.list_widget.addItem(item)
        message = f"找到 {len(self._tasks)} 个任务"
        if outside:
            message += f"，其中 {outside} 个不在当前显示的周"
        self.hint.setText(message)

    def _describe(self, task: Task, in_week: bool, now: datetime) -> str:
        flags = [status_label(task.status), priority_label(task.priority), task.category]
        if task.is_overdue(now):
            flags.append("逾期 " + remaining_label(task.due_at, now).replace("已逾期 ", ""))
        plans = len(task.plans)
        plan_text = f"{plans} 个计划时间" if plans else "无计划时间"
        location = "本周" if in_week else "其它周"
        return (
            f"{task.title}\n截止 {task.due_at.strftime('%Y-%m-%d %H:%M')} · {plan_text}"
            f" · {' · '.join(flags)} · {location}"
        )

    def _selected_task_id(self) -> int | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole) or 0)

    def _open_selected(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.task_activated.emit(task_id)
            self.accept()

    def _open_item(self, item: QListWidgetItem) -> None:
        task_id = int(item.data(Qt.ItemDataRole.UserRole) or 0)
        if task_id:
            self.task_activated.emit(task_id)
            self.accept()
