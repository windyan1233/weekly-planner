"""应用装配：数据库、提醒调度、系统通知、托盘与主窗口的唯一装配点。

主窗口不是提醒的必要条件：调度器、通知管理器、托盘都挂在这个对象上，
因此窗口隐藏到托盘、甚至从未打开时，提醒依然照常触发。
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, QSharedMemory, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import config, edition, icons, windows_integration
from .database import Database, DatabaseError
from .finance import FinanceService
from .global_hotkey import DEFAULT_HOTKEY, GlobalHotkey, describe_error
from .logging_setup import get_logger
from .main_window import MainWindow
from .notification_manager import NotificationManager
from .reminder_scheduler import (
    ReminderEngine,
    ReminderMessage,
    ReminderScheduler,
)
from .settings_store import SettingsStore
from .system_tray import SystemTray
from .task_manager import PlannerService
from .theme import ThemeManager
from .widgets import ReminderPopup

logger = get_logger("app")


class SingleInstance(QObject):
    """单实例保护：第二次启动只把参数交给已运行的实例。

    用 QSharedMemory 判断是否已有实例（Windows 上 QLocalServer 允许同名多个
    管道实例，不能作为唯一判据），用 QLocalSocket 转发参数（例如通知按钮的
    ``weeklyplanner://task/12``）。占用内存的进程退出后映射自动释放，不会残留。
    """

    activated = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        digest = hashlib.md5(str(config.app_data_dir()).lower().encode("utf-8")).hexdigest()[:12]
        self._name = f"weekly_planner_{digest}"
        self._memory = QSharedMemory(f"weekly_planner_shared_{digest}")
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._pending: list[str] = []

    @property
    def is_primary(self) -> bool:
        return bool(self._memory.isAttached())

    def acquire(self, message: str = "") -> bool:
        """返回 True 表示当前进程成为主实例。"""
        if self._memory.create(1):
            if message and message != "open":
                self._pending.append(message)
            if not self._server.listen(self._name):
                listen_error = self._server.errorString()
                QLocalServer.removeServer(self._name)
                if self._server.listen(self._name):
                    logger.info("单实例：清理残留管道后开始监听（%s）", listen_error)
                else:
                    logger.warning(
                        "单实例：无法创建消息管道（%s），通知按钮跳转可能不可用",
                        self._server.errorString(),
                    )
            logger.info("单实例：本进程成为主实例（%s）", self._name)
            return True

        # 已经有实例在运行：把参数转发过去，然后退出
        if message and message != "open":
            self._forward(message)
        else:
            self._forward("open")
        logger.info("单实例：检测到运行中的实例，已转交参数：%s", message or "open")
        return False

    def take_pending(self) -> list[str]:
        pending, self._pending = self._pending, []
        return pending

    # ------------------------------------------------------------------
    def _forward(self, message: str) -> bool:
        for _ in range(3):
            socket = QLocalSocket()
            socket.connectToServer(self._name)
            if socket.waitForConnected(900):
                socket.write(message.encode("utf-8"))
                socket.flush()
                socket.waitForBytesWritten(900)
                socket.disconnectFromServer()
                return True
            socket.abort()
            time.sleep(0.15)
        logger.warning("单实例：无法连接运行中的实例，参数未转交")
        return False

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.waitForReadyRead(500)
            data = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip()
            socket.disconnectFromServer()
            socket.deleteLater()
            self.activated.emit(data)
            if data and data != "open":
                self._pending.append(data)


class PlannerApplication(QObject):
    def __init__(
        self,
        app: QApplication,
        *,
        db_path: str | Path | None = None,
        start_minimized: bool | None = None,
        enable_tray: bool = True,
    ) -> None:
        super().__init__()
        self.app = app
        self._quitting = False
        self._popups: list[ReminderPopup] = []

        self.db = Database(db_path or config.database_path())
        self.settings = SettingsStore(self.db)
        self.engine = ReminderEngine(self.db, self.settings)
        self.service = PlannerService(self.db, self.settings)
        self.service.attach_engine(self.engine)
        self.theme_manager = ThemeManager(app)
        self.theme_manager.apply(self.settings.theme)

        # 记账模块：独立数据库文件，初始化失败也不影响日程
        self.finance: FinanceService | None = None
        try:
            finance_path = (
                Path(db_path).parent / "finance.db"
                if db_path is not None
                else config.finance_database_path()
            )
            self.finance = FinanceService(finance_path, schedule_db_path=self.db.path)
            written = self.finance.ensure_monthly_reports()
            logger.info(
                "记账模块已就绪：%s（月报快照写入 %s 个月）", finance_path, written
            )
            logger.info(
                "记账分类模式：%s",
                "可自定义" if edition.editable_categories() else "固定六类",
            )
        except Exception:  # noqa: BLE001 - 记账失败不能影响日程
            logger.exception("记账模块初始化失败，日程功能不受影响")
            self.finance = None

        self.notifier = NotificationManager(self.settings, parent=self)
        self.scheduler = ReminderScheduler(self.engine, self.settings, parent=self)
        self.hotkey = GlobalHotkey(self)
        self._hotkey_notice_shown = False

        self.tray: SystemTray | None = None
        self._tray_enabled = enable_tray and QSystemTrayIcon.isSystemTrayAvailable()
        if self._tray_enabled:
            self.tray = SystemTray(icons.app_icon(), self)
            self.notifier.set_tray_icon_provider(lambda: self.tray)

        self.window = MainWindow(
            self.service,
            self.theme_manager,
            scheduler=self.scheduler,
            tray=self.tray,
            notification_manager=self.notifier,
            hotkey_manager=self.hotkey,
            finance_service=self.finance,
        )
        self._wire()
        self._prepare_reminders()

        if start_minimized is None:
            start_minimized = self.settings.get_bool("start_minimized")
        self._start_minimized = start_minimized

        self.app.setQuitOnLastWindowClosed(False)
        if not self._tray_enabled:
            logger.warning("系统托盘不可用，关闭窗口将直接退出程序")
            self.app.setQuitOnLastWindowClosed(True)

    # ------------------------------------------------------------------
    def _wire(self) -> None:
        self.window.request_quit.connect(self.quit)
        self.scheduler.reminders_ready.connect(self._on_reminders_ready)
        self.scheduler.next_reminder_changed.connect(self._on_next_reminder)
        self.scheduler.error_occurred.connect(self._on_scheduler_error)
        self.scheduler.resynchronized.connect(self._on_resynchronized)
        self.notifier.popup_requested.connect(self._show_popup)
        self.notifier.failed.connect(lambda text: logger.warning(text))
        self.settings.add_listener(self._on_setting_changed)
        self.hotkey.activated.connect(self._on_hotkey_pressed)

        if self.tray is not None:
            self.tray.open_requested.connect(self.show_window)
            self.tray.add_requested.connect(self.add_task_from_tray)
            self.tray.settings_requested.connect(self.open_settings)
            self.tray.popup_toggled.connect(self._on_popup_toggled)
            self.tray.set_popup_enabled(self.settings.get_bool("inapp_notification"))
            self.tray.quit_requested.connect(self.quit)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()
            self.tray.set_next_reminder(None)

    def _prepare_reminders(self) -> None:
        # 启动时重建提醒，可以处理关机期间错过的提醒，也避免重复通知
        try:
            self.engine.rebuild_all()
        except DatabaseError as exc:
            logger.exception("启动时重建提醒失败")
            message = exc.user_message()  # 必须在这里取值：except 块结束后 exc 会被解绑
            QTimer.singleShot(
                0,
                lambda: QMessageBox.warning(self.window, "提醒初始化失败", message),
            )

    # ------------------------------------------------------------------
    def start(self) -> None:
        self.window.start(show_window=not self._start_minimized)
        self.scheduler.start()
        self._apply_hotkey()
        if self.settings.get_bool("system_notification"):
            ok, reason = windows_integration.ensure_toast_registration(icons.app_icon_path())
            logger.info("系统通知注册：%s %s", "成功" if ok else "失败", reason)
            protocol_ok, protocol_reason = windows_integration.register_protocol_handler()
            if not protocol_ok:
                logger.info("通知跳转协议注册失败：%s", protocol_reason)
        logger.info(
            "应用已启动：数据库 %s，托盘 %s，主题 %s",
            config.database_path(),
            "可用" if self.tray else "不可用",
            self.theme_manager.resolved,
        )
        if self.tray is not None:
            logger.info(
                "托盘状态：available=%s visible=%s（Windows 11 默认把新图标收进“^”溢出区）",
                QSystemTrayIcon.isSystemTrayAvailable(),
                self.tray.isVisible(),
            )
        else:
            logger.warning("系统托盘不可用，关闭窗口会直接退出程序")
        # 首次启动给一个轻提示，说明关闭窗口后仍在后台
        if self._start_minimized and self.tray is not None:
            self.tray.show_message(
                config.APP_DISPLAY_NAME,
                "已静默启动，截止提醒会在后台继续工作。",
                6000,
            )
        self._check_environment()

    # ------------------------------------------------------------------
    def _check_environment(self) -> None:
        """检测是否运行在受限环境（从聊天窗口/工具卡片启动时会被沙箱限制）。

        典型症状：写不了 HKCU（开机启动失败）、数据落到程序目录、托盘图标不出现。
        与其让用户对着一堆 WinError 5 发愣，不如启动时直接说清楚。
        """
        import os

        registry_ok = windows_integration.can_write_registry()
        data_dir = config.app_data_dir()
        fallback_dir = config.project_root() / "data"
        using_fallback = data_dir == fallback_dir
        if registry_ok and not using_fallback:
            return

        reasons = []
        if not registry_ok:
            reasons.append("无法写入当前用户的注册表（开机启动等设置会失败）")
        if using_fallback:
            reasons.append(f"无法写入用户的 AppData 目录，数据被存到了 {data_dir}")
        detail = "；".join(reasons)
        logger.warning("检测到受限运行环境：%s", detail)
        text = (
            "当前程序运行在受限环境中：\n"
            f"· {detail}\n\n"
            "这通常是因为从聊天窗口的文件卡片、或其他受限方式启动，进程被沙箱限制。\n\n"
            "请关闭本窗口，改为：双击开始菜单里的「一周日程」，\n"
            "或在资源管理器里打开 dist\\WeeklyPlanner\\WeeklyPlanner.exe 启动。"
        )
        if os.environ.get("WEEKLY_PLANNER_NO_ENV_WARNING") == "1":
            return
        QTimer.singleShot(0, lambda: QMessageBox.warning(self.window, "运行环境受限", text))

    def show_window(self) -> None:
        self.window.show_and_raise()

    # ------------------------------------------------------------------
    # 全局快捷键
    # ------------------------------------------------------------------
    def _apply_hotkey(self) -> None:
        if not self.settings.get_bool("hotkey_enabled"):
            self.hotkey.unregister()
            self.hotkey.clear_error()
            logger.info("全局快捷键：已关闭")
            return
        combo = self.settings.get_str("hotkey") or DEFAULT_HOTKEY
        ok, error = self.hotkey.register(combo)
        if ok:
            self._hotkey_notice_shown = False
            logger.info("全局快捷键已生效：%s", combo)
            return
        logger.warning("全局快捷键 %s 注册失败：%s", combo, describe_error(error))
        self._notify_hotkey_failure(combo, error)

    def _notify_hotkey_failure(self, combo: str, error: int) -> None:
        if self._hotkey_notice_shown:
            return
        self._hotkey_notice_shown = True
        text = (
            f"全局快捷键 {combo} 未生效：{describe_error(error)}。"
            "可以在「设置 → 启动与托盘」里换一个组合。"
        )
        if self.tray is not None:
            self.tray.show_message(config.APP_DISPLAY_NAME, text, 9000)
        else:
            self.window.show_notice(text)

    def _on_hotkey_pressed(self) -> None:
        # 有模态对话框打开时不要抢焦点，避免打断用户正在编辑的任务
        if QApplication.activeModalWidget() is not None:
            return
        logger.info("全局快捷键触发：显示窗口")
        self.show_window()

    def add_task_from_tray(self) -> None:
        self.show_window()
        self.window.add_task()

    def _on_popup_toggled(self, enabled: bool) -> None:
        self.settings.set("inapp_notification", enabled)

    def open_settings(self) -> None:
        self.show_window()
        self.window.open_settings()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.add_task_from_tray()

    # ------------------------------------------------------------------
    # 提醒
    # ------------------------------------------------------------------
    def _on_reminders_ready(self, messages: Iterable[ReminderMessage]) -> None:
        messages = list(messages)
        for message in messages:
            self.notifier.notify(message)
            logger.info("提醒触发：%s", message.title)
        late = [message for message in messages if message.late_label]
        if late:
            # 程序重启（或电脑睡眠）后补发的提醒，额外在底部提示一次，避免用户没看到通知
            logger.info("补发 %s 条错过的提醒", len(late))
            self.window.show_notice(f"已补发 {len(late)} 条错过的提醒（补发窗口内的提醒只补一次）")
        if self.window.isVisible():
            self.window.refresh()

    def _on_next_reminder(self, info) -> None:
        if self.tray is not None:
            self.tray.set_next_reminder(info)

    def _on_scheduler_error(self, text: str) -> None:
        logger.error("调度器错误：%s", text)
        if self.window.isVisible():
            self.window.show_notice(f"提醒检查失败：{text}")

    def _on_resynchronized(self, reason: str) -> None:
        logger.info("提醒已重新同步：%s", reason)
        if self.window.isVisible():
            self.window.refresh()
            self.window.show_notice(f"已重新检查提醒：{reason}")

    # ------------------------------------------------------------------
    # 应用内浮窗
    # ------------------------------------------------------------------
    def _show_popup(self, message: ReminderMessage) -> None:
        popup = ReminderPopup(
            message.title,
            message.body,
            task_id=message.task_id,
            reminder_id=message.reminder_id,
        )
        popup.view_requested.connect(self.open_task_from_notification)
        popup.snooze_requested.connect(
            lambda reminder_id, tid=message.task_id: self.snooze_from_notification(reminder_id, tid)
        )
        popup.dismissed.connect(lambda: self._popups.remove(popup) if popup in self._popups else None)
        self._popups.append(popup)
        self._position_popups()

    def _position_popups(self) -> None:
        screen = None
        if self.window.isVisible():
            screen = self.window.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        offset = 12
        for popup in reversed(self._popups):
            popup.adjustSize()
            height = popup.height()
            popup.resize(popup.width(), height)
            x = area.right() - popup.width() - 18
            y = area.bottom() - offset - height
            popup.move(max(area.left() + 8, x), max(area.top() + 8, y))
            popup.show()
            popup.raise_()
            offset += height + 10

    def open_task_from_notification(self, task_id: int) -> None:
        self.show_window()
        self.window.show_task_by_id(task_id)

    def snooze_from_notification(self, reminder_id, task_id: int = 0) -> None:
        target = None
        if reminder_id is not None:
            try:
                target = self.engine.snooze(int(reminder_id))
            except (DatabaseError, TypeError, ValueError):
                target = None
        if target is None and task_id:
            try:
                target = self.engine.snooze_task_due(int(task_id))
            except DatabaseError:
                target = None
        self._after_snooze(target)

    def _after_snooze(self, target) -> None:
        if target is None:
            logger.info("稍后提醒失败：找不到对应的提醒")
            return
        if self.window.isVisible():
            self.window.refresh()
        if self.tray is not None:
            info = self.engine.next_pending()
            if info is not None:
                reminder, task = info
                self.tray.set_next_reminder(
                    {"fire_at": reminder.fire_at, "title": task.title, "kind": reminder.kind}
                )
        logger.info("已推迟提醒到 %s", target.strftime("%Y-%m-%d %H:%M"))

    # ------------------------------------------------------------------
    # 协议 / 外部消息
    # ------------------------------------------------------------------
    def handle_activation(self, payload: str) -> None:
        """处理 ``weeklyplanner://task/12`` 之类的通知按钮跳转。"""
        text = (payload or "").strip()
        if not text or text == "open":
            self.show_window()
            return
        parsed = windows_integration.parse_protocol_url(text)
        if parsed is None:
            if text.isdigit():
                self.open_task_from_notification(int(text))
            else:
                self.show_window()
            return
        action, value = parsed
        if action in ("task", "open") and value.isdigit():
            self.open_task_from_notification(int(value))
        elif action == "snooze" and value.isdigit():
            self.snooze_from_notification(int(value))
        elif action == "add":
            self.add_task_from_tray()
        else:
            self.show_window()

    # ------------------------------------------------------------------
    def _on_setting_changed(self, key: str, value) -> None:
        if key == "theme":
            self.theme_manager.apply(self.settings.theme)
            self.window.apply_theme()
        elif key in ("reminder_mode", "previous_day_time", "missed_grace_hours"):
            try:
                self.engine.rebuild_all()
            except DatabaseError:
                logger.exception("设置变更后重建提醒失败")
            self.scheduler.tick()
        elif key in ("hotkey", "hotkey_enabled"):
            self._apply_hotkey()

    # ------------------------------------------------------------------
    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        logger.info("退出程序")
        try:
            self.scheduler.stop()
        except Exception:  # pragma: no cover
            pass
        try:
            self.hotkey.unregister()
        except Exception:  # pragma: no cover
            pass
        if self.tray is not None:
            self.tray.hide()
        try:
            self.window.force_close()
        except Exception:  # pragma: no cover
            pass
        try:
            self.db.close()
        except Exception:  # pragma: no cover
            pass
        self.app.quit()
