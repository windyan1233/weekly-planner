"""测试基础设施：临时数据库、Qt 应用、常用构造器。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Qt 测试使用 offscreen 平台，不需要真实桌面；必须在创建 QApplication 前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("WEEKLY_PLANNER_HOME", str(ROOT / ".testdata" / "_runtime"))

from src.database import Database  # noqa: E402
from src.models import PlanDraft, TaskDraft  # noqa: E402
from src.reminder_scheduler import ReminderEngine  # noqa: E402
from src.settings_store import SettingsStore  # noqa: E402
from src.task_manager import PlannerService  # noqa: E402

_APP = None


def qapp():
    """返回唯一的 QApplication（offscreen）。"""
    global _APP
    from PySide6.QtWidgets import QApplication

    _APP = QApplication.instance()
    if _APP is None:
        _APP = QApplication([])
    return _APP


class TestEnv:
    """一套隔离的数据库 + 服务层，供每个测试使用。

    临时目录放在项目内的 ``.testdata/cases``，避免受系统临时目录权限影响。
    """

    def __init__(self, name: str = "case") -> None:
        base = ROOT / ".testdata" / "cases"
        base.mkdir(parents=True, exist_ok=True)
        # 不使用 tempfile.mkdtemp：部分受限账户下它创建的目录不可写
        self.dir = base / f"{name}_{uuid.uuid4().hex[:8]}"
        self.dir.mkdir(parents=True, exist_ok=False)
        self.db_path = self.dir / "planner.db"
        self.open()

    def open(self) -> None:
        self.db = Database(self.db_path)
        self.settings = SettingsStore(self.db)
        self.engine = ReminderEngine(self.db, self.settings)
        self.service = PlannerService(self.db, self.settings)
        self.service.attach_engine(self.engine)

    def reopen(self) -> None:
        """模拟关闭并重新打开程序。"""
        self.db.close()
        self.open()

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    # ------------------------------------------------------------------
    def create_task(self, **kwargs) -> int:
        kwargs.setdefault("title", "测试任务")
        kwargs.setdefault("due_at", datetime.now() + timedelta(days=1))
        task = self.service.create_task(TaskDraft(**kwargs))
        return int(task.id or 0)

    def pending(self):
        return self.engine.pending_reminders()

    def reminder_rows(self, task_id: int, include_history: bool = True):
        return self.engine.reminders_for_task(task_id, include_history=include_history)

    def task_count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM tasks") or 0)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


def week_start_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def uid(prefix: str = "") -> str:
    return f"{prefix}{next(tempfile._get_candidate_names())}"
