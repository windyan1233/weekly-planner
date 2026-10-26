"""主窗口：一周视图 + 顶部工具栏 + 筛选 + 逾期提示。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import config, icons
from .courses.course_store import CourseStore
from .database import DatabaseError
from .finance import finance_icons
from .finance.finance_ui import FinanceUI
from .models import PRIORITIES, STATUSES, Task
from .search_dialog import SearchDialog
from .task_dialog import TaskDetailDialog, TaskDialog
from .task_manager import PlannerService, TaskFilter, TaskNotFoundError
from .theme import Palette, ThemeManager
from .time_utils import (
    month_label,
    remaining_label,
    start_of_week,
    week_days,
    week_number,
    week_range_label,
    weekday_label,
)
from .widgets import Card, FlowLayout, make_chip, make_icon_button
from .weekly_calendar import WeekView

FILTER_LABEL_STYLE = "color: %s; font-size: 11px;"


def _filter_label(text: str, color: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(FILTER_LABEL_STYLE % color)
    label.setContentsMargins(6, 0, 2, 0)
    return label


class MainWindow(QMainWindow):
    """应用主窗口。构造后调用 :meth:`start` 初始化定时器。"""

    request_quit = Signal()

    def __init__(
        self,
        service: PlannerService,
        theme_manager: ThemeManager,
        *,
        scheduler=None,
        tray=None,
        notification_manager=None,
        hotkey_manager=None,
        finance_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.settings = service.settings
        self.theme_manager = theme_manager
        self.scheduler = scheduler
        self.tray = tray
        self.notification_manager = notification_manager
        self.hotkey_manager = hotkey_manager
        self.finance_service = finance_service
        self.course_store: CourseStore | None = None
        try:
            self.course_store = CourseStore(self.service.db)
        except Exception:  # noqa: BLE001 - 课程表不可用不影响任务
            self.course_store = None
        self.finance_ui = FinanceUI(finance_service, theme_manager, self)
        self.finance_ui.navigate_requested.connect(self._set_page)

        self._now = datetime.now()
        self._today = self._now.date()
        self._now_line_stamp = datetime.min
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._on_search_changed)
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._on_clock_tick)
        self._tray_hint_shown = False

        self.filter = TaskFilter()
        self._follow_today = True
        self._category_buttons: dict[str, QPushButton] = {}
        self._filter_groups: list[QButtonGroup] = []
        self._overdue_actions: list[QWidget] = []
        self._last_category_signature: tuple[str, ...] = ()
        self._quitting = False

        self.setWindowTitle(f"{config.APP_DISPLAY_NAME} · 一周日程")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1080, 640)
        self._build_ui()
        self._install_shortcuts()
        self._apply_palette()
        self._restore_geometry()
        self._update_clock_labels()
        self._navigate(start_of_week(self._today), follow=True)

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(10)

        root.addWidget(self._build_nav_bar())
        self._pages = QStackedWidget()
        root.addWidget(self._pages, 1)

        schedule_page = QWidget()
        schedule_layout = QVBoxLayout(schedule_page)
        schedule_layout.setContentsMargins(0, 0, 0, 0)
        schedule_layout.setSpacing(10)
        schedule_layout.addWidget(self._build_header())
        schedule_layout.addWidget(self._build_filter_bar())
        self._overdue_banner = self._build_overdue_banner()
        schedule_layout.addWidget(self._overdue_banner)
        self._search_banner = self._build_search_banner()
        schedule_layout.addWidget(self._search_banner)

        self.week_view = WeekView(self.theme_manager.palette, self._now, self)
        self.week_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.week_view.task_clicked.connect(self.open_task)
        self.week_view.task_context_requested.connect(self._show_task_menu)
        self.week_view.slot_clicked.connect(self._on_slot_clicked)
        self.week_view.add_requested.connect(self._on_day_clicked)
        self.week_view.course_clicked.connect(self._show_course_info)
        schedule_layout.addWidget(self.week_view, 1)

        schedule_layout.addWidget(self._build_footer())
        self._pages.addWidget(schedule_page)
        for key in ("overview", "report", "accounts"):
            self._pages.addWidget(self.finance_ui.page(key))
        self._set_page("schedule")

    # ------------------------------------------------------------------
    def _build_nav_bar(self) -> QWidget:
        card = Card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 7, 12, 7)
        layout.setSpacing(6)

        icon_label = QLabel()
        icon_label.setPixmap(icons.app_icon().pixmap(22, 22))
        layout.addWidget(icon_label)
        brand = QLabel(config.APP_DISPLAY_NAME)
        brand.setObjectName("NavBrand")
        layout.addWidget(brand)
        layout.addSpacing(12)

        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for key, title in (
            ("schedule", "日程"),
            ("overview", "记账"),
            ("report", "月度总结"),
            ("accounts", "资金管理"),
        ):
            button = QPushButton(title)
            button.setObjectName("NavTab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, page=key: self._set_page(page))
            layout.addWidget(button)
            self._nav_group.addButton(button)
            self._nav_buttons[key] = button

        layout.addStretch(1)

        self.help_button = QPushButton("?")
        self.help_button.setObjectName("IconButton")
        self.help_button.setFixedSize(34, 32)
        self.help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_button.setToolTip("使用说明")
        self.help_button.setStyleSheet("font-size: 15px;")
        self.help_button.clicked.connect(self.open_help)
        layout.addWidget(self.help_button)

        self.theme_button = QPushButton("◐")
        self.theme_button.setObjectName("IconButton")
        self.theme_button.setFixedSize(34, 32)
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setToolTip("切换浅色 / 深色主题")
        self.theme_button.setStyleSheet("font-size: 16px;")
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)

        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setFixedSize(34, 32)
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("设置")
        self.settings_button.setStyleSheet("font-size: 15px;")
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)
        return card

    def _set_page(self, key: str) -> None:
        order = {"schedule": 0, "overview": 1, "report": 2, "accounts": 3}
        if key not in order:
            return
        self._pages.setCurrentIndex(order[key])
        for name, button in self._nav_buttons.items():
            button.setChecked(name == key)
        self._update_nav_icons()
        if key != "schedule":
            self.finance_ui.refresh_all()

    def _update_nav_icons(self) -> None:
        palette = self.theme_manager.palette
        current = self._pages.currentIndex() if hasattr(self, "_pages") else 0
        keys = ["schedule", "overview", "report", "accounts"]
        for index, key in enumerate(keys):
            button = self._nav_buttons.get(key)
            if button is None:
                continue
            color = palette.accent if index == current else palette.text_secondary
            button.setIcon(finance_icons.app_nav_icon(key, color, 16))

    # ------------------------------------------------------------------
    def _build_header(self) -> QWidget:
        card = Card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 12, 16, 12)
        layout.setSpacing(14)

        month_box = QVBoxLayout()
        month_box.setSpacing(2)
        self.month_label = QLabel()
        self.month_label.setObjectName("Title")
        month_box.addWidget(self.month_label)
        self.week_range_label = QLabel()
        self.week_range_label.setObjectName("Subtitle")
        month_box.addWidget(self.week_range_label)
        layout.addLayout(month_box)

        self._header_separator = QFrame()
        self._header_separator.setFixedWidth(1)
        self._header_separator.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._header_separator)

        today_box = QVBoxLayout()
        today_box.setSpacing(0)
        self.today_label = QLabel()
        self.today_label.setObjectName("Subtitle")
        today_box.addWidget(self.today_label)
        self.clock_label = QLabel()
        clock_font = QFont()
        clock_font.setPixelSize(21)
        clock_font.setWeight(QFont.Weight.DemiBold)
        self.clock_label.setFont(clock_font)
        today_box.addWidget(self.clock_label)
        layout.addLayout(today_box, 0)

        layout.addStretch(1)

        self.prev_button = make_icon_button(icons.chevron_icon("left", "#888888", 16), "上一周 (Ctrl+←)")
        self.prev_button.clicked.connect(lambda: self._shift_week(-1))
        layout.addWidget(self.prev_button)

        self.today_button = QPushButton("本周")
        self.today_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_button.setToolTip("回到今天所在的周 (Ctrl+T)")
        self.today_button.clicked.connect(self.go_today)
        layout.addWidget(self.today_button)

        self.next_button = make_icon_button(icons.chevron_icon("right", "#888888", 16), "下一周 (Ctrl+→)")
        self.next_button.clicked.connect(lambda: self._shift_week(1))
        layout.addWidget(self.next_button)

        layout.addSpacing(4)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("SearchInput")
        self.search_edit.setPlaceholderText("搜索任务…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(200)
        self._search_action = self.search_edit.addAction(
            icons.search_icon("#8A91A6", 16), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_edit.textChanged.connect(lambda _: self._search_timer.start())
        self.search_edit.returnPressed.connect(self.open_search_dialog)
        self.search_edit.setToolTip("在全部日期中搜索（回车打开结果列表，Ctrl+F 聚焦）")
        layout.addWidget(self.search_edit)

        self.import_courses_button = QPushButton("导入课表")
        self.import_courses_button.setObjectName("Ghost")
        self.import_courses_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_courses_button.setToolTip("从教务系统导出的 .xls 课表导入")
        self.import_courses_button.clicked.connect(self.open_timetable_import)
        layout.addWidget(self.import_courses_button)

        self.add_button = QPushButton("新建任务")
        self.add_button.setObjectName("Primary")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setIcon(icons.plus_icon("#FFFFFF", 16))
        self.add_button.setIconSize(QSize(15, 15))
        self.add_button.setToolTip("新建任务 (Ctrl+N)")
        self.add_button.clicked.connect(lambda: self.add_task())
        layout.addWidget(self.add_button)
        return card

    # ------------------------------------------------------------------
    def _build_filter_bar(self) -> QWidget:
        card = Card()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(2)
        self._filter_flow = FlowLayout(hspacing=4, vspacing=4)
        layout.addLayout(self._filter_flow)
        self._rebuild_filters()
        return card

    def _rebuild_filters(self) -> None:
        palette = self.theme_manager.palette
        while self._filter_flow.count():
            item = self._filter_flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for group in self._filter_groups:
            group.deleteLater()
        self._filter_groups = []
        self._category_buttons = {}

        categories = self.service.categories()
        self._last_category_signature = tuple(categories)

        self._add_chip_group(
            "分类",
            [("", "全部")] + [(name, name) for name in categories],
            self.filter.category,
            self._set_category,
            palette,
        )
        self._add_chip_group(
            "状态",
            [("", "全部")] + list(STATUSES),
            self.filter.status,
            self._set_status,
            palette,
        )
        self._add_chip_group(
            "优先级",
            [("", "全部")] + list(PRIORITIES),
            self.filter.priority,
            self._set_priority,
            palette,
        )
        spacing = QWidget()
        spacing.setFixedWidth(8)
        self._filter_flow.addWidget(spacing)

        overdue_chip = make_chip("仅看逾期")
        overdue_chip.setChecked(self.filter.overdue_only)
        overdue_chip.setToolTip("只显示已经超过截止时间的任务")
        overdue_chip.clicked.connect(self._toggle_overdue_filter)
        self._filter_flow.addWidget(overdue_chip)

    def _add_chip_group(
        self,
        label: str,
        options,
        current: str,
        setter: Callable[[str], None],
        palette: Palette,
    ) -> None:
        self._filter_flow.addWidget(_filter_label(label, palette.text_muted))
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, text in options:
            chip = make_chip(text)
            chip.setChecked(key == current)
            chip.clicked.connect(lambda _checked=False, k=key: setter(k))
            group.addButton(chip)
            self._filter_flow.addWidget(chip)
        self._filter_groups.append(group)

    def _set_category(self, value: str) -> None:
        self.filter.category = value
        self.refresh()

    def _set_status(self, value: str) -> None:
        self.filter.status = value
        self.refresh()

    def _set_priority(self, value: str) -> None:
        self.filter.priority = value
        self.refresh()

    def _toggle_overdue_filter(self) -> None:
        self.filter.overdue_only = not self.filter.overdue_only
        self._rebuild_filters()
        self.refresh()

    # ------------------------------------------------------------------
    def _build_overdue_banner(self) -> QWidget:
        card = Card(soft=True)
        self._overdue_layout = QHBoxLayout(card)
        self._overdue_layout.setContentsMargins(12, 8, 12, 8)
        self._overdue_layout.setSpacing(8)
        card.hide()
        return card

    def _build_search_banner(self) -> QWidget:
        card = Card(soft=True)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        self._search_banner_label = QLabel()
        self._search_banner_label.setObjectName("Subtitle")
        layout.addWidget(self._search_banner_label)
        layout.addStretch(1)
        self._search_all_button = QPushButton("查看全部搜索结果")
        self._search_all_button.setObjectName("Link")
        self._search_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_all_button.clicked.connect(self.open_search_dialog)
        layout.addWidget(self._search_all_button)
        card.hide()
        return card

    def _build_footer(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(8)
        self.stats_label = QLabel()
        self.stats_label.setObjectName("Subtitle")
        layout.addWidget(self.stats_label)
        self.notice_label = QLabel()
        self.notice_label.setObjectName("Subtitle")
        self.notice_label.hide()
        layout.addWidget(self.notice_label)
        layout.addStretch(1)
        self.local_label = QLabel("数据仅保存在本机")
        self.local_label.setObjectName("Subtitle")
        layout.addWidget(self.local_label)
        return widget

    def show_notice(self, text: str, msecs: int = 7000) -> None:
        """在底部显示一条临时提示（不占用额外空间）。"""
        self.notice_label.setText(text)
        self.notice_label.show()
        QTimer.singleShot(msecs, self._clear_notice)

    def _clear_notice(self) -> None:
        self.notice_label.hide()
        self.notice_label.setText("")

    def apply_theme(self) -> None:
        self._apply_palette()

    def _install_shortcuts(self) -> None:
        for sequence, slot in (
            ("Ctrl+N", lambda: self.add_task()),
            ("Ctrl+F", self._focus_search),
            ("Ctrl+T", self.go_today),
            ("Ctrl+Left", lambda: self._shift_week(-1)),
            ("Ctrl+Right", lambda: self._shift_week(1)),
            ("F5", self.refresh),
            ("Ctrl+Shift+F", self.open_search_dialog),
            ("Ctrl+,", self.open_settings),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)

    # ==================================================================
    # 主题
    # ==================================================================
    def _apply_palette(self) -> None:
        palette = self.theme_manager.palette
        muted = palette.text_muted
        self.prev_button.setIcon(icons.chevron_icon("left", muted, 16))
        self.next_button.setIcon(icons.chevron_icon("right", muted, 16))
        self._search_action.setIcon(icons.search_icon(muted, 16))
        self._header_separator.setStyleSheet(f"background-color: {palette.border}; border: none;")
        self.week_view.set_palette(palette)
        self._update_nav_icons()
        self.finance_ui.apply_palette(palette)
        self._rebuild_filters()
        self._refresh_banners()
        self.update()

    def toggle_theme(self) -> None:
        current = self.settings.theme
        new_theme = "dark" if self.theme_manager.resolved == "light" else "light"
        self.settings.set("theme", new_theme)
        self.theme_manager.apply(new_theme)
        self._apply_palette()
        self._update_clock_labels()
        _ = current

    # ==================================================================
    # 刷新
    # ==================================================================
    def refresh(self, *, reload_filters: bool = False) -> None:
        self._now = datetime.now()
        self._today = self._now.date()
        if tuple(self.service.categories()) != self._last_category_signature or reload_filters:
            self._rebuild_filters()
        try:
            occurrences = self.service.occurrences(self.week_view.week_start(), self.filter, now=self._now)
            summary = self.service.week_summary(self.week_view.week_start(), self.filter)
            overdue = self.service.overdue_tasks(now=self._now)
        except DatabaseError as exc:
            self._show_database_error(exc)
            return
        self.week_view.set_now(self._now)
        self.week_view.set_occurrences(occurrences)
        blocks = []
        if self.course_store is not None:
            try:
                blocks = self.course_store.blocks_between(
                    self.week_view.week_start(), self.week_view.week_end()
                )
            except Exception:  # noqa: BLE001 - 课程表异常不影响任务
                blocks = []
        self.week_view.set_course_blocks(blocks)
        self._update_header()
        self._update_footer(summary)
        self._refresh_overdue_banner(overdue)
        self._refresh_search_banner()

    def _update_header(self) -> None:
        week_start = self.week_view.week_start()
        week_end = self.week_view.week_end()
        self.month_label.setText(month_label(week_start))
        self.week_range_label.setText(
            f"{week_range_label(week_start, week_end)} · 第 {week_number(week_start)} 周"
        )
        following = week_start == start_of_week(self._today)
        self.today_button.setEnabled(not following)
        self.today_button.setToolTip("已经是本周" if following else "回到今天所在的周 (Ctrl+T)")

    def _update_clock_labels(self) -> None:
        now = self._now
        self.today_label.setText(f"今天 {now.month} 月 {now.day} 日 {weekday_label(now)}")
        self.clock_label.setText(now.strftime("%H:%M:%S"))

    def _update_footer(self, summary) -> None:
        parts = [
            f"本周 {summary.week_events} 项安排",
            f"已完成 {summary.done}",
            f"全部 {summary.total_tasks} 项任务",
        ]
        if summary.pending_reminders:
            parts.append(f"待触发提醒 {summary.pending_reminders} 条")
        self.stats_label.setText(" · ".join(parts))
        self.local_label.setText(f"本地数据库 · {config.database_path()}")

    def _refresh_overdue_banner(self, overdue: list[Task]) -> None:
        while self._overdue_layout.count():
            item = self._overdue_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if not overdue or self.filter.overdue_only:
            self._overdue_banner.hide()
            return
        palette = self.theme_manager.palette
        title = QLabel(f"已逾期 {len(overdue)} 项")
        title.setStyleSheet(f"color: {palette.danger}; font-weight: 600;")
        self._overdue_layout.addWidget(title)
        for task in overdue[:4]:
            button = QPushButton(task.title)
            button.setObjectName("OverdueChip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"{task.title}\n截止 {task.due_text()}\n{remaining_label(task.due_at, self._now)}")
            button.clicked.connect(lambda _=False, tid=int(task.id or 0): self.open_task(tid))
            button.setMaximumWidth(210)
            self._overdue_layout.addWidget(button)
        if len(overdue) > 4:
            more = QLabel(f"等 {len(overdue)} 项")
            more.setObjectName("Subtitle")
            self._overdue_layout.addWidget(more)
        self._overdue_layout.addStretch(1)
        show_all = QPushButton("只看逾期")
        show_all.setObjectName("Link")
        show_all.setCursor(Qt.CursorShape.PointingHandCursor)
        show_all.clicked.connect(self._toggle_overdue_filter)
        self._overdue_layout.addWidget(show_all)
        self._overdue_banner.show()

    def _refresh_banners(self) -> None:
        try:
            self._refresh_overdue_banner(self.service.overdue_tasks(now=self._now))
        except DatabaseError:
            pass
        self._refresh_search_banner()

    def _refresh_search_banner(self) -> None:
        needle = self.search_edit.text().strip() if hasattr(self, "search_edit") else ""
        if not needle:
            self._search_banner.hide()
            return
        try:
            hits = self.service.search_tasks(needle)
        except DatabaseError:
            self._search_banner.hide()
            return
        week = set(week_days(self.week_view.week_start()))
        outside = [
            task
            for task in hits
            if not any(day in week for day in task.visible_dates())
        ]
        if not outside:
            self._search_banner.hide()
            return
        self._search_banner_label.setText(
            f"搜索「{needle}」：{len(hits)} 个匹配任务中有 {len(outside)} 个不在本周"
        )
        self._search_all_button.setText(f"查看全部 {len(hits)} 个结果")
        self._search_banner.show()

    def _on_search_changed(self) -> None:
        self.filter.search = self.search_edit.text().strip()
        self.refresh()

    def _focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ==================================================================
    # 时间
    # ==================================================================
    def _on_clock_tick(self) -> None:
        self._now = datetime.now()
        self._update_clock_labels()
        today_changed = self._now.date() != self._today
        if today_changed:
            self._today = self._now.date()
            self.week_view.set_now(self._now, scroll_if_today=True)
            if self._follow_today:
                self._navigate(start_of_week(self._today), follow=True)
            else:
                self._update_header()
                self.refresh()
            self._now_line_stamp = self._now
            if self.scheduler is not None:
                self.scheduler.tick(now=self._now)
            self.finance_ui.on_date_changed(self._now)
            return
        if (self._now - self._now_line_stamp).total_seconds() >= 20:
            self._now_line_stamp = self._now
            self.week_view.set_now(self._now)

    # ==================================================================
    # 导航
    # ==================================================================
    def _navigate(self, week_date: date, *, follow: bool) -> None:
        self._follow_today = follow
        self.week_view.set_week(week_date)
        self._update_header()
        self.refresh()

    def _shift_week(self, weeks: int) -> None:
        new_week = self.week_view.week_start() + timedelta(weeks=weeks)
        self._navigate(new_week, follow=False)

    def go_today(self) -> None:
        self._navigate(start_of_week(self._today), follow=True)
        self.week_view.scroll_to_now()

    # ==================================================================
    # 任务操作
    # ==================================================================
    def add_task(
        self,
        *,
        due: datetime | None = None,
        plan: datetime | None = None,
        day: date | None = None,
    ) -> None:
        dialog = TaskDialog(self.service, self, initial_due=due, initial_plan=plan, initial_date=day)
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            self._after_dialog(dialog.saved_task_id, dialog.was_deleted)

    def _on_slot_clicked(self, day: date, qtime) -> None:
        plan = datetime(day.year, day.month, day.day, qtime.hour(), qtime.minute())
        due = plan + timedelta(hours=3)
        self.add_task(due=due, plan=plan)

    def _on_day_clicked(self, day: date) -> None:
        self.add_task(day=day)

    def _after_dialog(self, task_id: int | None, deleted: bool) -> None:
        if deleted or task_id is None:
            self.refresh(reload_filters=True)
            return
        try:
            task = self.service.get_task(task_id)
        except TaskNotFoundError:
            self.refresh(reload_filters=True)
            return
        dates = task.visible_dates()
        visible = set(week_days(self.week_view.week_start()))
        if not any(day in visible for day in dates):
            self._navigate(
                start_of_week(dates[0]),
                follow=start_of_week(dates[0]) == start_of_week(self._today),
            )
        else:
            self.refresh(reload_filters=True)

    def open_task(self, task_id: int) -> None:
        if not task_id:
            return
        try:
            dialog = TaskDetailDialog(self.service, task_id, self)
        except TaskNotFoundError:
            self.refresh()
            return
        dialog.changed.connect(lambda: self.refresh(reload_filters=True))
        dialog.exec()
        self.refresh(reload_filters=True)

    def _edit_task(self, task_id: int) -> None:
        try:
            task = self.service.get_task(task_id)
        except TaskNotFoundError:
            return
        dialog = TaskDialog(self.service, self, task=task)
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            self._after_dialog(dialog.saved_task_id, dialog.was_deleted)

    def _toggle_task_done(self, task_id: int) -> None:
        try:
            self.service.toggle_done(task_id)
        except (TaskNotFoundError, DatabaseError) as exc:
            self._show_operation_error(exc)
            return
        self.refresh()

    def _duplicate_task(self, task_id: int) -> None:
        try:
            task = self.service.duplicate_task(task_id)
        except (TaskNotFoundError, DatabaseError) as exc:
            self._show_operation_error(exc)
            return
        self.refresh(reload_filters=True)
        self._after_dialog(int(task.id or 0), False)

    def _delete_task(self, task_id: int) -> None:
        try:
            task = self.service.get_task(task_id)
        except TaskNotFoundError:
            self.refresh()
            return
        answer = QMessageBox.question(
            self,
            "删除任务",
            f"确定要删除「{task.title}」吗？\n相关计划时间和待触发提醒会一并删除，此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete_task(task_id)
        except DatabaseError as exc:
            self._show_database_error(exc)
            return
        self.refresh(reload_filters=True)

    def _shift_task_week(self, task_id: int, weeks: int) -> None:
        try:
            task = self.service.get_task(task_id)
        except TaskNotFoundError:
            return
        delta = timedelta(weeks=weeks)
        draft = self._draft_from_task(task)
        draft.due_at = task.due_at + delta
        for plan in draft.plans:
            plan.plan_at = plan.plan_at + delta
        try:
            self.service.update_task(task_id, draft)
        except DatabaseError as exc:
            self._show_database_error(exc)
            return
        self.refresh()

    @staticmethod
    def _draft_from_task(task: Task):
        from .models import TaskDraft

        return TaskDraft.from_task(task)

    def _show_task_menu(self, task_id: int, global_pos: QPoint) -> None:
        try:
            task = self.service.get_task(task_id)
        except TaskNotFoundError:
            return
        menu = QMenu(self)
        view = menu.addAction("查看详情")
        edit = menu.addAction("编辑任务")
        done_label = "标记为未开始" if task.status == "done" else "标记完成"
        toggle = menu.addAction(done_label)
        menu.addSeparator()
        duplicate = menu.addAction("复制任务")
        move_next = menu.addAction("整体顺延一周")
        menu.addSeparator()
        delete = menu.addAction("删除任务…")
        chosen = menu.exec(global_pos)
        if chosen is view:
            self.open_task(task_id)
        elif chosen is edit:
            self._edit_task(task_id)
        elif chosen is toggle:
            self._toggle_task_done(task_id)
        elif chosen is duplicate:
            self._duplicate_task(task_id)
        elif chosen is move_next:
            self._shift_task_week(task_id, 1)
        elif chosen is delete:
            self._delete_task(task_id)

    # ==================================================================
    # 其它入口
    # ==================================================================
    def open_search_dialog(self) -> None:
        dialog = SearchDialog(
            self.service, self, initial_text=self.search_edit.text().strip(), current_week=self._now
        )
        dialog.task_activated.connect(self._open_from_search)
        dialog.exec()

    def _open_from_search(self, task_id: int) -> None:
        try:
            task = self.service.get_task(task_id)
        except TaskNotFoundError:
            return
        dates = task.visible_dates()
        visible = set(week_days(self.week_view.week_start()))
        if not any(day in visible for day in dates):
            self._navigate(start_of_week(dates[0]), follow=start_of_week(dates[0]) == start_of_week(self._today))
        self.open_task(task_id)

    def open_help(self) -> None:
        from .help_dialog import HelpDialog

        HelpDialog(self).exec()

    def open_settings(self) -> None:
        from .settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QDialog

        dialog = SettingsDialog(
            self.service,
            self.settings,
            self.service.engine,
            self,
            theme_manager=self.theme_manager,
            notification_manager=self.notification_manager,
            hotkey_manager=self.hotkey_manager,
            finance=self.finance_service,
        )
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.data_restored.connect(self._on_data_restored)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._on_settings_changed()
            if dialog.restored:
                self._on_data_restored()

    def _on_settings_changed(self) -> None:
        self.theme_manager.apply(self.settings.theme)
        if self.tray is not None:
            self.tray.set_popup_enabled(self.settings.get_bool("inapp_notification"))
        self._apply_palette()
        self.refresh(reload_filters=True)

    def _on_data_restored(self) -> None:
        self._apply_palette()
        if self.finance_service is not None:
            try:
                self.finance_ui.refresh_all()
            except Exception:  # noqa: BLE001
                pass
        self._navigate(start_of_week(self._today), follow=True)

    # ==================================================================
    # 错误提示
    # ==================================================================
    def _show_database_error(self, exc: DatabaseError) -> None:
        QMessageBox.critical(
            self,
            "数据读写失败",
            exc.user_message()
            + "\n\n建议：点击「设置 → 立即备份」保存现有数据，然后检查磁盘空间或数据目录权限。",
        )

    def _show_operation_error(self, exc: Exception) -> None:
        if isinstance(exc, DatabaseError):
            self._show_database_error(exc)
        else:
            QMessageBox.warning(self, "操作失败", str(exc))

    # ==================================================================
    # 窗口行为
    # ==================================================================
    def start(self, show_window: bool = True) -> None:
        self._clock_timer.start()
        if show_window:
            self.show()
            self.raise_()

    def _restore_geometry(self) -> None:
        geometry = self.settings.get_str("window_geometry")
        restored = False
        if geometry:
            try:
                import binascii

                self.restoreGeometry(binascii.a2b_base64(geometry.encode("ascii")))
                restored = True
            except (ValueError, binascii.Error):
                restored = False
        if not restored:
            screen = self.screen().availableGeometry() if self.screen() else None
            if screen is not None:
                width = min(1420, screen.width() - 40)
                height = min(900, screen.height() - 60)
                self.resize(width, height)
            else:
                self.resize(1360, 860)
            self.move(0, 0)

    def _save_geometry(self) -> None:
        try:
            import binascii

            data = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.settings.set("window_geometry", data)
        except (ValueError, AttributeError):
            pass

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_geometry()
        tray_available = self.tray is not None and self.tray.isVisible()
        if not self._quitting and self.settings.get_bool("close_to_tray") and tray_available:
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.show_message(
                    config.APP_DISPLAY_NAME,
                    "程序已最小化到系统托盘，截止提醒会继续在后台工作。"
                    "如果任务栏右下角看不到图标，点一下「^」展开隐藏的图标；右键图标可以退出。",
                    9000,
                )
            return
        if not self._quitting and self.settings.get_bool("close_to_tray") and not tray_available:
            # 不在这里弹模态框（关窗口时弹窗反而让人以为程序卡住），
            # 启动时已提示过受限环境。
            pass
        self._save_geometry()
        event.accept()
        self.request_quit.emit()

    def force_close(self) -> None:
        self._quitting = True
        self.close()

    def open_timetable_import(self) -> None:
        if self.course_store is None:
            QMessageBox.warning(self, "导入课表", "课程表模块不可用，请查看日志。")
            return
        from .courses.import_dialog import TimetableImportDialog

        dialog = TimetableImportDialog(self.course_store, self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.show_notice("课表已导入：课程会作为背景显示在周视图里。")

    def _show_course_info(self, block) -> None:
        lines = [block.name, f"{block.day:%Y-%m-%d}  {block.time_label}"]
        if block.teacher:
            lines.append(f"教师：{block.teacher}")
        if block.location:
            lines.append(f"地点：{block.location}")
        QMessageBox.information(self, "课程安排", "\n".join(lines))

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_task_by_id(self, task_id: int) -> None:
        self.show_and_raise()
        self._open_from_search(task_id)
