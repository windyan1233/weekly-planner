"""系统托盘：关闭窗口后程序仍驻留在此，保证提醒不中断。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from . import config
from .time_utils import humanize_delta


class SystemTray(QSystemTrayIcon):
    open_requested = Signal()
    add_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    popup_toggled = Signal(bool)

    def __init__(self, icon: QIcon, parent: QWidget | None = None) -> None:
        super().__init__(icon, parent)
        self.setToolTip(config.APP_DISPLAY_NAME)

        menu = QMenu()
        self._open_action = menu.addAction("打开日程表")
        self._add_action = menu.addAction("添加任务")
        self._settings_action = menu.addAction("设置")
        self._popup_action = menu.addAction("显示应用内提醒浮窗")
        self._popup_action.setCheckable(True)
        self._popup_action.setChecked(True)
        menu.addSeparator()
        self._info_action = menu.addAction("暂无待触发提醒")
        self._info_action.setEnabled(False)
        menu.addSeparator()
        self._quit_action = menu.addAction("退出程序")
        self._menu = menu
        self.setContextMenu(menu)

        self._open_action.triggered.connect(self.open_requested)
        self._add_action.triggered.connect(self.add_requested)
        self._settings_action.triggered.connect(self.settings_requested)
        self._popup_action.triggered.connect(lambda checked=False: self.popup_toggled.emit(bool(checked)))
        self._quit_action.triggered.connect(self.quit_requested)
        self.activated.connect(self._on_activated)

    # ------------------------------------------------------------------
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_requested.emit()

    # ------------------------------------------------------------------
    def set_next_reminder(self, info: dict | None) -> None:
        if not info:
            self._info_action.setText("暂无待触发提醒")
            self.setToolTip(f"{config.APP_DISPLAY_NAME} · 暂无待触发提醒")
            return
        fire_at: datetime = info.get("fire_at") or datetime.now()
        title = str(info.get("title") or "")
        remaining = humanize_delta(fire_at - datetime.now())
        self._info_action.setText(f"下一条提醒：{fire_at.strftime('%m-%d %H:%M')} · {title}")
        self.setToolTip(
            f"{config.APP_DISPLAY_NAME}\n下一条提醒：{fire_at.strftime('%m月%d日 %H:%M')}（{remaining}）\n{title}"
        )

    def set_popup_enabled(self, enabled: bool) -> None:
        self._popup_action.setChecked(enabled)

    def set_summary(self, text: str) -> None:
        self.setToolTip(f"{config.APP_DISPLAY_NAME}\n{text}")

    def show_message(self, title: str, body: str, msecs: int = 8000) -> None:
        """在系统托盘弹出通知（Windows 10/11 会进入通知中心）。"""
        if not self.isVisible():
            return
        self.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, msecs)

    def notify(self, title: str, message: str, msecs: int = 12000) -> None:
        self.show_message(title, message, msecs)
