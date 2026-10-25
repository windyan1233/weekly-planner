"""用户设置（保存在同一个 SQLite 数据库的 settings 表里）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any, Callable

from .database import Database
from .models import DEFAULT_CATEGORIES
from .time_utils import MODE_BEFORE_DUE_24H, parse_time

DEFAULTS: dict[str, Any] = {
    "theme": "light",                       # light / dark / system
    "reminder_mode": MODE_BEFORE_DUE_24H,   # 截止前 24 小时 / 前一天指定时间
    "previous_day_time": "09:00",
    "missed_grace_hours": 12,               # 重启后多久之内的错过提醒会补发
    "system_notification": True,            # Windows 系统通知
    "inapp_notification": True,             # 应用内浮窗
    "notification_sound": True,
    "close_to_tray": True,
    "start_minimized": False,
    "hotkey_enabled": True,                 # 全局快捷键：按一次唤出窗口
    "hotkey": "Ctrl+Shift+R",
    "autostart": False,                     # 界面状态，真实状态以注册表为准
    "snooze_minutes": 10,
    "categories": list(DEFAULT_CATEGORIES),
    "default_category": DEFAULT_CATEGORIES[0],
    "last_backup_at": "",
    "window_geometry": "",
    "last_reminder_notice": "",             # 避免重复提示「错过的提醒」
}

THEME_LABELS = {
    "light": "浅色",
    "dark": "深色",
    "system": "跟随系统",
}


@dataclass(frozen=True)
class ReminderPolicy:
    mode: str = MODE_BEFORE_DUE_24H
    previous_day_time: str = "09:00"
    grace_hours: int = 12

    @property
    def previous_day_clock(self) -> time:
        return parse_time(self.previous_day_time)


class SettingsStore:
    """带默认值、类型校正和变更通知的设置门面。"""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._cache: dict[str, Any] = {}
        self._listeners: list[Callable[[str, Any], None]] = []
        self._cache = db.all_settings()

    # ------------------------------------------------------------------
    def add_listener(self, callback: Callable[[str, Any], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, key: str, value: Any) -> None:
        for callback in list(self._listeners):
            callback(key, value)

    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        if key in self._cache:
            value = self._cache[key]
        elif key in DEFAULTS:
            value = DEFAULTS[key]
        else:
            return default
        return value

    def get_bool(self, key: str) -> bool:
        return bool(self.get(key, False))

    def get_int(self, key: str) -> int:
        try:
            return int(self.get(key, 0))
        except (TypeError, ValueError):
            return 0

    def get_str(self, key: str) -> str:
        value = self.get(key, "")
        return "" if value is None else str(value)

    def set(self, key: str, value: Any, *, persist: bool = True) -> None:
        if self._cache.get(key) == value:
            return
        self._cache[key] = value
        if persist:
            self._db.set_setting(key, value)
        self._notify(key, value)

    def update(self, values: dict[str, Any]) -> None:
        changed: dict[str, Any] = {}
        for key, value in values.items():
            if self._cache.get(key) != value:
                changed[key] = value
        if not changed:
            return
        self._cache.update(changed)
        for key, value in changed.items():
            self._db.set_setting(key, value)
        for key, value in changed.items():
            self._notify(key, value)

    # ------------------------------------------------------------------
    @property
    def theme(self) -> str:
        theme = self.get_str("theme") or "light"
        return theme if theme in THEME_LABELS else "light"

    @property
    def categories(self) -> list[str]:
        value = self.get("categories", list(DEFAULT_CATEGORIES))
        if not isinstance(value, list):
            value = list(DEFAULT_CATEGORIES)
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or list(DEFAULT_CATEGORIES)

    def add_category(self, name: str) -> bool:
        name = name.strip()
        if not name:
            return False
        categories = self.categories
        if name in categories:
            return False
        categories.append(name)
        self.set("categories", categories)
        return True

    def reminder_policy(self) -> ReminderPolicy:
        mode = self.get_str("reminder_mode") or MODE_BEFORE_DUE_24H
        previous = self.get_str("previous_day_time") or "09:00"
        try:
            parse_time(previous)
        except ValueError:
            previous = "09:00"
        grace = self.get_int("missed_grace_hours")
        if grace <= 0:
            grace = 12
        return ReminderPolicy(mode=mode, previous_day_time=previous, grace_hours=grace)

    def snooze_minutes(self) -> int:
        minutes = self.get_int("snooze_minutes")
        return minutes if minutes > 0 else 10
