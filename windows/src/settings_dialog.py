"""设置窗口：外观、提醒规则、启动与托盘、数据备份。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from . import config, windows_integration
from .database import DatabaseError
from .global_hotkey import DEFAULT_HOTKEY, HOTKEY_PRESETS, describe_error, parse_hotkey
from .reminder_scheduler import ReminderEngine
from .settings_store import SettingsStore, THEME_LABELS
from .task_manager import PlannerService
from .theme import current_palette
from .time_utils import MODE_BEFORE_DUE_24H, MODE_PREVIOUS_DAY_AT, REMINDER_MODE_LABELS, parse_time
from .widgets import Card, section_title


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


class SettingsDialog(QDialog):
    settings_changed = Signal()
    data_restored = Signal()

    def __init__(
        self,
        service: PlannerService,
        settings: SettingsStore,
        engine: ReminderEngine | None = None,
        parent: QWidget | None = None,
        *,
        theme_manager=None,
        notification_manager=None,
        hotkey_manager=None,
        finance=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._settings = settings
        self._engine = engine
        self._theme_manager = theme_manager
        self._notification_manager = notification_manager
        self._hotkey_manager = hotkey_manager
        self._finance = finance
        self._original_hotkey = (settings.get_bool("hotkey_enabled"), settings.get_str("hotkey"))
        self._restored = False
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.resize(680, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(12)

        title = QLabel("设置")
        title.setObjectName("Title")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(2, 2, 10, 2)
        layout.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # -- 外观 ----------------------------------------------------------
        layout.addWidget(section_title("外观"))
        appearance = Card()
        appearance_layout = QVBoxLayout(appearance)
        appearance_layout.setContentsMargins(16, 14, 16, 14)
        appearance_layout.setSpacing(8)
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        for key, label in THEME_LABELS.items():
            self.theme_combo.addItem(label, key)
        index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(0, index))
        self.theme_combo.setFixedWidth(180)
        self.theme_combo.currentIndexChanged.connect(self._apply_theme_preview)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        appearance_layout.addLayout(theme_row)
        appearance_layout.addWidget(_muted("深色主题适合夜间使用，设置为「跟随系统」时会自动跟随 Windows 的浅色/深色模式。"))
        layout.addWidget(appearance)

        # -- 提醒 ----------------------------------------------------------
        layout.addWidget(section_title("提醒"))
        reminder_card = Card()
        reminder_layout = QVBoxLayout(reminder_card)
        reminder_layout.setContentsMargins(16, 14, 16, 14)
        reminder_layout.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("截止前一天提醒方式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(REMINDER_MODE_LABELS[MODE_BEFORE_DUE_24H], MODE_BEFORE_DUE_24H)
        self.mode_combo.addItem(REMINDER_MODE_LABELS[MODE_PREVIOUS_DAY_AT], MODE_PREVIOUS_DAY_AT)
        mode_index = self.mode_combo.findData(settings.get_str("reminder_mode"))
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        self.mode_combo.setFixedWidth(230)
        self.mode_combo.currentIndexChanged.connect(self._sync_mode_widgets)
        mode_row.addWidget(self.mode_combo)
        mode_row.addSpacing(12)
        mode_row.addWidget(QLabel("前一天的时间"))
        self.previous_day_edit = QTimeEdit(parse_time(settings.get_str("previous_day_time")))
        self.previous_day_edit.setDisplayFormat("HH:mm")
        self.previous_day_edit.setFixedWidth(86)
        mode_row.addWidget(self.previous_day_edit)
        mode_row.addStretch(1)
        reminder_layout.addLayout(mode_row)
        reminder_layout.addWidget(
            _muted("示例：截止时间为 10 月 25 日 18:00 时，默认在 10 月 24 日 18:00 提醒；"
                   "选择「前一天指定时间」则可以在 10 月 24 日 09:00 提醒。")
        )

        grace_row = QHBoxLayout()
        grace_row.addWidget(QLabel("错过提醒的补发窗口"))
        self.grace_spin = QSpinBox()
        self.grace_spin.setRange(1, 168)
        self.grace_spin.setSuffix(" 小时")
        self.grace_spin.setValue(max(1, settings.get_int("missed_grace_hours")))
        self.grace_spin.setFixedWidth(110)
        grace_row.addWidget(self.grace_spin)
        grace_row.addSpacing(16)
        grace_row.addWidget(QLabel("稍后提醒间隔"))
        self.snooze_spin = QSpinBox()
        self.snooze_spin.setRange(1, 240)
        self.snooze_spin.setSuffix(" 分钟")
        self.snooze_spin.setValue(settings.snooze_minutes())
        self.snooze_spin.setFixedWidth(110)
        grace_row.addWidget(self.snooze_spin)
        grace_row.addStretch(1)
        reminder_layout.addLayout(grace_row)
        reminder_layout.addWidget(
            _muted("程序未运行时（关机、退出）不会弹出通知；重新打开后，在补发窗口内的提醒会补发一次，"
                   "更早的提醒会标记为错过，不会反复弹窗。")
        )

        self.system_notify_check = QCheckBox("使用 Windows 系统通知（推荐）")
        self.system_notify_check.setChecked(settings.get_bool("system_notification"))
        reminder_layout.addWidget(self.system_notify_check)
        self.inapp_notify_check = QCheckBox("同时显示应用内提醒浮窗")
        self.inapp_notify_check.setChecked(settings.get_bool("inapp_notification"))
        reminder_layout.addWidget(self.inapp_notify_check)
        self.sound_check = QCheckBox("播放提示音")
        self.sound_check.setChecked(settings.get_bool("notification_sound"))
        reminder_layout.addWidget(self.sound_check)

        test_row = QHBoxLayout()
        test_row.addStretch(1)
        self.test_button = QPushButton("发送测试通知")
        self.test_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_button.clicked.connect(self._send_test_notification)
        test_row.addWidget(self.test_button)
        reminder_layout.addLayout(test_row)
        layout.addWidget(reminder_card)

        # -- 启动与托盘 ----------------------------------------------------
        layout.addWidget(section_title("启动与托盘"))
        startup_card = Card()
        startup_layout = QVBoxLayout(startup_card)
        startup_layout.setContentsMargins(16, 14, 16, 14)
        startup_layout.setSpacing(8)
        self.autostart_check = QCheckBox("开机时自动启动（登录 Windows 后静默运行在系统托盘）")
        self.autostart_check.setChecked(windows_integration.is_autostart_enabled())
        startup_layout.addWidget(self.autostart_check)
        if not windows_integration.is_windows():
            self.autostart_check.setEnabled(False)
            startup_layout.addWidget(_muted("当前系统不是 Windows，开机启动不可用。"))
        self.close_to_tray_check = QCheckBox("点击关闭按钮时最小化到系统托盘（继续在后台提醒）")
        self.close_to_tray_check.setChecked(settings.get_bool("close_to_tray"))
        startup_layout.addWidget(self.close_to_tray_check)
        self.start_minimized_check = QCheckBox("启动时直接最小化到托盘")
        self.start_minimized_check.setChecked(settings.get_bool("start_minimized"))
        startup_layout.addWidget(self.start_minimized_check)
        startup_layout.addWidget(_muted("只有托盘菜单里的「退出程序」会真正结束进程并停止提醒。"))

        separator = QFrame()
        separator.setObjectName("Separator")
        separator.setFixedHeight(1)
        startup_layout.addWidget(separator)

        self.hotkey_check = QCheckBox("启用全局快捷键：在任何程序里按一次即可唤出日程表")
        self.hotkey_check.setChecked(settings.get_bool("hotkey_enabled"))
        startup_layout.addWidget(self.hotkey_check)

        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(8)
        hotkey_row.addWidget(QLabel("快捷键"))
        self.hotkey_combo = QComboBox()
        self.hotkey_combo.setEditable(True)
        self.hotkey_combo.addItems(HOTKEY_PRESETS)
        stored_combo = settings.get_str("hotkey") or DEFAULT_HOTKEY
        if self.hotkey_combo.findText(stored_combo) < 0:
            self.hotkey_combo.addItem(stored_combo)
        self.hotkey_combo.setCurrentText(stored_combo)
        self.hotkey_combo.setFixedWidth(190)
        hotkey_row.addWidget(self.hotkey_combo)
        self.hotkey_status = QLabel("")
        self.hotkey_status.setObjectName("Subtitle")
        hotkey_row.addWidget(self.hotkey_status)
        hotkey_row.addStretch(1)
        startup_layout.addLayout(hotkey_row)
        startup_layout.addWidget(
            _muted(
                "全局快捷键会抢占所有程序的这个组合（例如浏览器里的 Ctrl+Shift+R 强制刷新、"
                "VS Code 的「重新加载窗口」）。程序需要驻留在托盘；组合被其它程序占用时会提示你换一个。"
            )
        )
        if not windows_integration.is_windows():
            self.hotkey_check.setEnabled(False)
            self.hotkey_combo.setEnabled(False)
            self.hotkey_status.setText("当前系统不支持")
        elif not self._hotkey_available():
            self.hotkey_check.setChecked(False)
            self.hotkey_check.setEnabled(False)
            self.hotkey_combo.setEnabled(False)
            self.hotkey_status.setText("未接入快捷键管理器")
        self.hotkey_check.toggled.connect(self.hotkey_combo.setEnabled)
        self.hotkey_combo.setEnabled(self.hotkey_check.isChecked())
        self._refresh_hotkey_status()

        layout.addWidget(startup_card)

        # -- 数据 ----------------------------------------------------------
        layout.addWidget(section_title("数据"))
        data_card = Card()
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(16, 14, 16, 14)
        data_layout.setSpacing(8)
        stats = self._service.db.stats()
        size_kb = max(1, self._service.db.file_size() // 1024)
        data_layout.addWidget(
            _muted(
                f"数据文件：{config.database_path()}\n"
                f"共 {stats['tasks']} 个任务、{stats['plans']} 个计划时间、"
                f"{stats['pending_reminders']} 条待触发提醒（{size_kb} KB）。"
            )
        )
        data_layout.addWidget(_muted("所有数据只保存在本机，不会上传到云端。"))
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        for text, slot in (
            ("打开数据文件夹", self._open_folder),
            ("立即备份", self._backup),
            ("从备份恢复", self._restore),
            ("导出 CSV", self._export_csv),
            ("导入 CSV", self._import_csv),
        ):
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            buttons_row.addWidget(button)
        buttons_row.addStretch(1)
        data_layout.addLayout(buttons_row)

        json_row = QHBoxLayout()
        json_row.setSpacing(8)
        for text, slot in (("导出 JSON", self._export_json), ("导入 JSON", self._import_json)):
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            json_row.addWidget(button)
        json_row.addStretch(1)
        data_layout.addLayout(json_row)
        layout.addWidget(data_card)

        # -- 关于 ----------------------------------------------------------
        layout.addWidget(section_title("关于"))
        about_card = Card(soft=True)
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(16, 12, 16, 12)
        about_layout.setSpacing(4)
        about_layout.addWidget(_muted(f"一周日程 v{config.APP_VERSION} · Python + PySide6 + SQLite"))
        about_layout.addWidget(
            _muted("一周只显示一周，任务可含多个计划时间；重启后数据仍在，提醒由后台调度器独立执行。")
        )
        author_row = QHBoxLayout()
        author_row.setSpacing(8)
        author_button = QPushButton("作者的话")
        author_button.setCursor(Qt.CursorShape.PointingHandCursor)
        author_button.clicked.connect(self._show_author_note)
        author_row.addWidget(author_button)
        author_row.addStretch(1)
        about_layout.addLayout(author_row)
        layout.addWidget(about_card)
        layout.addStretch(1)

        # -- 底部 ----------------------------------------------------------
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._save)
        footer.addWidget(save)
        root.addLayout(footer)

        self._sync_mode_widgets()

    # ------------------------------------------------------------------
    def _sync_mode_widgets(self) -> None:
        mode = self.mode_combo.currentData()
        self.previous_day_edit.setEnabled(mode == MODE_PREVIOUS_DAY_AT)

    # ------------------------------------------------------------------
    # 全局快捷键
    # ------------------------------------------------------------------
    def _hotkey_available(self) -> bool:
        return self._hotkey_manager is not None

    def _refresh_hotkey_status(self) -> None:
        if self._hotkey_manager is None:
            return
        status = getattr(self._hotkey_manager, "status_text", lambda: "")()
        self.hotkey_status.setText(status or "")
        registered = getattr(self._hotkey_manager, "is_registered", lambda: False)()
        self.hotkey_status.setStyleSheet(
            f"color: {current_palette().success};" if registered else ""
        )

    def _validate_hotkey(self) -> tuple[bool, str]:
        combo = self.hotkey_combo.currentText().strip()
        try:
            parse_hotkey(combo)
        except ValueError as exc:
            return False, str(exc)
        return True, combo

    def _apply_theme_preview(self) -> None:
        theme = str(self.theme_combo.currentData())
        if self._theme_manager is not None:
            self._theme_manager.apply(theme)

    def reject(self) -> None:  # noqa: D401
        # 取消时恢复原来的主题，避免「预览」被误当成已保存
        if self._theme_manager is not None:
            self._theme_manager.apply(self._settings.theme)
        # 取消时也要还原本来的全局快捷键（保存前可能已经试注册过）
        if self._hotkey_manager is not None:
            enabled, combo = self._original_hotkey
            if enabled and combo:
                self._hotkey_manager.register(combo)
            else:
                self._hotkey_manager.unregister()
                self._hotkey_manager.clear_error()
        super().reject()

    # ------------------------------------------------------------------
    def _save(self) -> None:
        mode = str(self.mode_combo.currentData())
        previous = self.previous_day_edit.time().toString("HH:mm")

        # 先处理全局快捷键：注册失败就留在设置里让用户换一个，不保存设置
        hotkey_enabled = self.hotkey_check.isChecked()
        hotkey_combo = self.hotkey_combo.currentText().strip()
        if hotkey_enabled:
            valid, message = self._validate_hotkey()
            if not valid:
                QMessageBox.warning(self, "快捷键格式不正确", message + "（例如 Ctrl+Shift+R）")
                return
            hotkey_combo = message
            if self._hotkey_manager is not None:
                ok, error = self._hotkey_manager.register(hotkey_combo)
                if not ok:
                    self._refresh_hotkey_status()
                    QMessageBox.warning(
                        self,
                        "快捷键不可用",
                        f"{hotkey_combo} 无法注册：{describe_error(error)}。\n\n"
                        "请换一个组合（例如 Ctrl+Alt+F8），或取消勾选「启用全局快捷键」。",
                    )
                    return
                self._refresh_hotkey_status()
        elif self._hotkey_manager is not None:
            self._hotkey_manager.unregister()
            self._hotkey_manager.clear_error()
            self._refresh_hotkey_status()

        try:
            self._settings.update(
                {
                    "theme": str(self.theme_combo.currentData()),
                    "reminder_mode": mode,
                    "previous_day_time": previous,
                    "missed_grace_hours": int(self.grace_spin.value()),
                    "snooze_minutes": int(self.snooze_spin.value()),
                    "system_notification": self.system_notify_check.isChecked(),
                    "inapp_notification": self.inapp_notify_check.isChecked(),
                    "notification_sound": self.sound_check.isChecked(),
                    "close_to_tray": self.close_to_tray_check.isChecked(),
                    "start_minimized": self.start_minimized_check.isChecked(),
                    "hotkey_enabled": hotkey_enabled,
                    "hotkey": hotkey_combo,
                }
            )
        except DatabaseError as exc:
            QMessageBox.critical(self, "保存设置失败", exc.user_message())
            return
        if self._theme_manager is not None:
            self._theme_manager.apply(self._settings.theme)
        ok, reason = windows_integration.set_autostart(
            self.autostart_check.isChecked(), start_minimized=True
        )
        if not ok and self.autostart_check.isChecked():
            QMessageBox.warning(
                self,
                "开机启动设置失败",
                (reason or "未知原因")
                + "\n\n如果程序是从聊天窗口的文件卡片或其他受限方式启动的，"
                "写注册表会一直被拒绝。请改为双击开始菜单里的「一周日程」再设置。",
            )
        try:
            self._settings.set("autostart", self.autostart_check.isChecked())
        except DatabaseError as exc:
            QMessageBox.critical(self, "保存设置失败", exc.user_message())
            return
        if self._engine is not None:
            try:
                self._engine.rebuild_all()
            except DatabaseError as exc:
                QMessageBox.critical(self, "重建提醒失败", exc.user_message())
        self.settings_changed.emit()
        self.accept()

    # ------------------------------------------------------------------
    def _send_test_notification(self) -> None:
        if self._notification_manager is not None:
            channel = self._notification_manager.send_test()
            QMessageBox.information(
                self, "测试通知", f"已通过以下通道发送：{channel}\n如果没看到系统通知，请检查 Windows 通知设置。"
            )
        else:
            QMessageBox.information(self, "测试通知", "当前无法发送测试通知（通知管理器未就绪）。")

    def _open_folder(self) -> None:
        ok, reason = windows_integration.open_folder(config.app_data_dir())
        if not ok:
            QMessageBox.warning(self, "打开失败", reason)

    def _backup(self) -> None:
        default_name = f"planner-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.db"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "备份数据库",
            str(Path.home() / default_name),
            "SQLite 数据库 (*.db)",
        )
        if not path:
            return
        try:
            self._service.backup_to(path)
        except DatabaseError as exc:
            QMessageBox.critical(self, "备份失败", exc.user_message())
            return
        self._settings.set("last_backup_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
        QMessageBox.information(self, "备份完成", f"已备份到：\n{path}")

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件", str(Path.home()), "SQLite 数据库 (*.db);;所有文件 (*.*)"
        )
        if not path:
            return
        ok, reason = self._service.db.validate_backup(path)
        if not ok:
            QMessageBox.warning(self, "无法恢复", reason)
            return
        answer = QMessageBox.question(
            self,
            "从备份恢复",
            "恢复会用备份文件覆盖当前数据。\n当前数据库会先另存为 planner.before-restore.db。\n\n确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.restore_from(path)
        except DatabaseError as exc:
            QMessageBox.critical(self, "恢复失败", exc.user_message())
            return
        self._restored = True
        self.data_restored.emit()
        QMessageBox.information(self, "恢复完成", "数据已恢复，界面会立即刷新。")
        self.accept()

    def _export_csv(self) -> None:
        default_name = f"planner-{datetime.now().strftime('%Y%m%d')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", str(Path.home() / default_name), "CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            count = self._service.export_csv(path)
        except DatabaseError as exc:
            QMessageBox.critical(self, "导出失败", exc.user_message())
            return
        QMessageBox.information(self, "导出完成", f"已导出 {count} 个任务到：\n{path}")

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 CSV", str(Path.home()), "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            result = self._service.import_csv(path)
        except DatabaseError as exc:
            QMessageBox.critical(self, "导入失败", exc.user_message())
            return
        QMessageBox.information(
            self,
            "导入完成",
            f"新增 {result['tasks']} 个任务、{result['plans']} 个计划时间。"
            + (f"\n跳过 {result['skipped']} 行（缺少名称或时间）。" if result["skipped"] else ""),
        )
        self.settings_changed.emit()

    def _show_author_note(self) -> None:
        from .author_note import AuthorNoteDialog

        AuthorNoteDialog(self).exec()

    def _export_json(self) -> None:
        from .exchange import export_to_file

        finance = self._finance
        if finance is None:
            QMessageBox.warning(self, "导出 JSON", "财务模块未连接，无法导出。")
            return
        default_name = f"weekly-planner-{datetime.now().strftime('%Y%m%d-%H%M')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 JSON 数据",
            str(Path.home() / default_name),
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            payload = export_to_file(self._service.db, finance.db, Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", f"导出 JSON 失败：\n{exc}")
            return
        summary = (
            f"{len(payload.get('tasks', []))} 个任务、"
            f"{len(payload.get('transactions', []))} 条账目、"
            f"{len(payload.get('courses', []))} 门课程"
        )
        QMessageBox.information(
            self,
            "导出完成",
            f"已导出到：\n{path}\n\n包含 {summary}。\n"
            "把文件发到手机后，在安卓版「我的 → 数据 → 恢复备份」里选择它即可导入。",
        )

    def _import_json(self) -> None:
        from .exchange import import_from_file

        finance = self._finance
        if finance is None:
            QMessageBox.warning(self, "导入 JSON", "财务模块未连接，无法导入。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入 JSON 数据",
            str(Path.home()),
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "导入 JSON",
            "导入会用 JSON 文件整体替换当前的任务、课程、账目、资金分区和月报。\n\n确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            counts = import_from_file(self._service.db, finance.db, Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", f"导入 JSON 失败：\n{exc}")
            return
        try:
            engine = self._service.engine
            if engine is not None:
                engine.rebuild_all()
        except Exception:  # noqa: BLE001
            pass
        self._restored = True
        self.data_restored.emit()
        self.settings_changed.emit()
        QMessageBox.information(
            self,
            "导入完成",
            f"任务 {counts['tasks']} 个、课程 {counts['courses']} 门、"
            f"账目 {counts['transactions']} 条、资金分区 {counts['accounts']} 个。",
        )

    @property
    def restored(self) -> bool:
        return self._restored
