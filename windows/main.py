"""一周日程（Weekly Planner）程序入口。

用法::

    python main.py                # 正常启动，显示本周
    python main.py --minimized    # 静默启动到系统托盘（开机自启动使用）
    python main.py "weeklyplanner://task/12"   # 从系统通知跳转到任务
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 启动阶段的诊断日志：写在临时目录，不依赖数据库/数据目录是否可用。
# 如果程序在打开窗口之前就退出，看这个文件就知道停在哪一步。
_BOOTSTRAP_LOG = Path(os.environ.get("TEMP") or ".") / "WeeklyPlanner-bootstrap.log"


def _bootstrap(message: str) -> None:
    try:
        with open(_BOOTSTRAP_LOG, "a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except OSError:
        pass


def _qt_message_handler(mode, context, message) -> None:  # pragma: no cover - 只在异常时用到
    _bootstrap(f"Qt[{mode}] {message}")


def _prepare_high_dpi() -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    # 桌面程序必须用 windows 平台插件；外部环境若留下 QT_QPA_PLATFORM（例如 offscreen）
    # Qt 可能加载不到插件后直接退出，这里显式指定，且允许用 WEEKLY_PLANNER_PLATFORM 覆盖。
    if sys.platform == "win32":
        os.environ["QT_QPA_PLATFORM"] = os.environ.get("WEEKLY_PLANNER_PLATFORM", "windows")
    elif os.environ.get("WEEKLY_PLANNER_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = os.environ["WEEKLY_PLANNER_PLATFORM"]
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # pragma: no cover - 老系统上忽略
            pass
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "WeeklyPlanner.Desktop"
            )
        except Exception:  # pragma: no cover
            pass


def _install_exception_hook(logger) -> None:
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _bootstrap("未捕获的异常：\n" + text)
        logger.error("未捕获的异常：\n%s", text)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None,
                    "程序出现错误",
                    f"发生未预期的错误，详细信息已写入日志：\n{text[-800:]}",
                )
        except Exception:  # pragma: no cover
            pass

    sys.excepthook = hook


def _run(args: list[str]) -> int:
    from src.logging_setup import get_logger, setup_logging

    setup_logging()
    logger = get_logger("main")
    _install_exception_hook(logger)
    _bootstrap("日志已初始化")

    from PySide6.QtCore import Qt, QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox

    from src import config, icons
    from src.app import PlannerApplication, SingleInstance
    from src.database import DatabaseError

    def _handler(mode, context, message) -> None:
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            _qt_message_handler(mode, context, message)

    qInstallMessageHandler(_handler)

    if "--help" in args or "-h" in args:
        print(__doc__)
        print(f"数据目录：{config.app_data_dir()}")
        return 0

    _bootstrap(f"创建 QApplication，参数={args}，QT_QPA_PLATFORM={os.environ.get('QT_QPA_PLATFORM')}")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(args)
    _bootstrap(f"QApplication 创建成功，平台={app.platformName()}")
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_DISPLAY_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(icons.app_icon())
    _bootstrap("图标与基础属性设置完成")

    font = QFont()
    font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Arial"])
    font.setPixelSize(13)
    app.setFont(font)

    minimized = "--minimized" in args or "--background" in args
    external = [
        item
        for item in args[1:]
        if item.lower().startswith(f"{config.PROTOCOL_SCHEME}://") or item.isdigit()
    ]
    first_message = external[0] if external else "open"

    _bootstrap("单实例检查")
    instance = SingleInstance()
    if not instance.acquire(first_message):
        logger.info("已有实例在运行，参数已转交：%s", first_message)
        _bootstrap("已有实例在运行，本进程退出")
        return 0
    _bootstrap("成为主实例")

    try:
        context = PlannerApplication(
            app,
            start_minimized=True if minimized else None,
        )
    except DatabaseError as exc:
        logger.exception("数据库初始化失败")
        _bootstrap("数据库初始化失败：" + exc.user_message())
        QMessageBox.critical(
            None,
            "无法启动",
            exc.user_message()
            + "\n\n请检查数据目录权限，或从设置中恢复一个备份。\n"
            + f"数据目录：{config.app_data_dir()}",
        )
        return 1
    _bootstrap("应用对象创建完成")

    instance.activated.connect(context.handle_activation)
    context.start()
    _bootstrap("窗口/托盘/调度器已启动")
    # 首次以通知按钮参数启动时，处理被转交的那条消息（只处理一次）
    for pending in instance.take_pending():
        if pending and pending != "open":
            context.handle_activation(pending)
    logger.info("进入事件循环")
    _bootstrap("进入事件循环")
    code = app.exec()
    _bootstrap(f"事件循环结束，退出码 {code}")
    return code


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv)
    _bootstrap(
        f"=== 启动 pid={os.getpid()} frozen={bool(getattr(sys, 'frozen', False))} "
        f"cwd={os.getcwd()} argv={args} ==="
    )
    try:
        _prepare_high_dpi()
        return _run(args)
    except BaseException:
        _bootstrap("启动失败：\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
