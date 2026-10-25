"""应用级常量与路径解析。

数据默认保存在 ``%APPDATA%\\WeeklyPlanner``，重启电脑、重装程序（只要不清除
该目录）都不会丢失。测试或便携使用时可用环境变量 ``WEEKLY_PLANNER_HOME``
指向别的目录。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "WeeklyPlanner"
APP_DISPLAY_NAME = "一周日程"
APP_VERSION = "1.0.2"
APP_AUMID = "WeeklyPlanner.Desktop"          # Windows 通知标识
APP_REGISTRY_NAME = "WeeklyPlanner"          # 开机启动注册表值名
PROTOCOL_SCHEME = "weeklyplanner"            # 通知按钮跳转协议

ENV_DATA_HOME = "WEEKLY_PLANNER_HOME"

# 提醒调度节拍（秒）。20 秒足够精确到分钟，同时开销极低。
TICK_INTERVAL_SECONDS = 20


_DATA_DIR_CACHE: Path | None = None


def _ensure_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def app_data_dir() -> Path:
    """返回数据目录（数据库、日志、备份都在这里）。

    默认 ``%APPDATA%\\WeeklyPlanner``。只有当该位置**确实无法使用**时，才退回到
    程序目录下的 ``data`` 和用户主目录——如果那里已经有数据库，就坚持用它，
    哪怕一次写入探测失败（例如杀毒软件短暂锁定），避免把数据分裂到第二个目录。
    """
    global _DATA_DIR_CACHE
    if _DATA_DIR_CACHE is not None:
        return _DATA_DIR_CACHE

    override = os.environ.get(ENV_DATA_HOME, "").strip()
    if override:
        path = Path(override).expanduser()
        if not _ensure_writable(path):
            raise OSError(f"数据目录不可写：{path}")
        _DATA_DIR_CACHE = path
        return path

    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        candidates = [
            Path(base) / APP_NAME,
            project_root() / "data",
            Path.home() / f".{APP_NAME.lower()}",
        ]
    else:  # 测试/跨平台时的回退
        candidates = [
            Path.home() / f".{APP_NAME.lower()}",
            project_root() / "data",
        ]

    for candidate in candidates:
        if _ensure_writable(candidate):
            _DATA_DIR_CACHE = candidate
            return candidate
        if (candidate / "planner.db").exists():
            # 目录里已经有数据库：继续用它，写不进去时让上层给出明确错误，
            # 而不是悄悄把数据放到另一个目录里
            _DATA_DIR_CACHE = candidate
            return candidate
    # 全都不行时仍然返回第一个，让上层给出明确的错误信息
    _DATA_DIR_CACHE = candidates[0]
    return _DATA_DIR_CACHE


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return app_data_dir() / "planner.db"


def finance_database_path() -> Path:
    """记账模块使用独立数据库文件，与日程库互不影响。"""
    return app_data_dir() / "finance.db"


def backup_dir() -> Path:
    path = app_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    """项目根目录（打包后为可执行文件所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_launch_command(include_placeholder: bool = False) -> str:
    """返回用于注册表 / 通知跳转的命令行。

    ``include_placeholder=True`` 时附带 ``"%1"``，供 URL 协议与通知按钮使用。
    """
    exe, args = app_executable_and_args()
    command = f'"{exe}"'
    if args:
        command += f" {args}"
    if include_placeholder:
        command += ' "%1"'
    return command


def app_executable_and_args() -> tuple[str, str]:
    """返回 (可执行文件, 参数串)，用于创建快捷方式。"""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), ""
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else python
    main_py = project_root() / "main.py"
    return str(exe), f'"{main_py}"'
