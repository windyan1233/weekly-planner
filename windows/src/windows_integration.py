"""Windows 集成：开机自启、通知跳转协议、提示音。

所有函数在失败时返回 ``(False, 原因)`` 而不是抛出异常，界面可据此提示用户。
非 Windows 平台下会安全降级（返回 False），不会让程序崩溃。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import config
from .logging_setup import get_logger

logger = get_logger("windows")

_IS_WINDOWS = sys.platform == "win32"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_CLASSES_KEY = r"Software\Classes"


def is_windows() -> bool:
    return _IS_WINDOWS


def _winreg():
    import winreg  # noqa: PLC0415 - 仅 Windows 可用

    return winreg


# --------------------------------------------------------------------------
# 开机自动启动
# --------------------------------------------------------------------------
def autostart_command(start_minimized: bool = True) -> str:
    command = config.app_launch_command(include_placeholder=False)
    if start_minimized:
        command += " --minimized"
    return command


def is_autostart_enabled() -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, config.APP_REGISTRY_NAME)
        return True
    except OSError:
        return False


def can_write_registry() -> bool:
    """当前进程能否写 HKCU（受限 / 沙箱环境会返回 False）。"""
    if not _IS_WINDOWS:
        return False
    try:
        winreg = _winreg()
        path = rf"Software\{config.APP_NAME}\Probe"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.SetValueEx(key, "ok", 0, winreg.REG_SZ, "1")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool, *, start_minimized: bool = True) -> tuple[bool, str]:
    if not _IS_WINDOWS:
        return False, "当前系统不是 Windows，无法设置开机启动。"
    try:
        winreg = _winreg()
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                command = autostart_command(start_minimized)
                winreg.SetValueEx(key, config.APP_REGISTRY_NAME, 0, winreg.REG_SZ, command)
                logger.info("已启用开机自启：%s", command)
            else:
                try:
                    winreg.DeleteValue(key, config.APP_REGISTRY_NAME)
                    logger.info("已关闭开机自启")
                except FileNotFoundError:
                    pass
        return True, ""
    except OSError as exc:
        logger.warning("设置开机自启失败：%s", exc)
        return False, str(exc)


# --------------------------------------------------------------------------
# URL 协议（通知按钮「查看任务」/「稍后提醒」）
# --------------------------------------------------------------------------
def protocol_command() -> str:
    return config.app_launch_command(include_placeholder=True)


def register_protocol_handler() -> tuple[bool, str]:
    if not _IS_WINDOWS:
        return False, "当前系统不是 Windows。"
    scheme = config.PROTOCOL_SCHEME
    base = rf"{_CLASSES_KEY}\{scheme}"
    try:
        winreg = _winreg()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{config.APP_DISPLAY_NAME}")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(key, "FriendlyTypeName", 0, winreg.REG_SZ, config.APP_DISPLAY_NAME)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, protocol_command())
        logger.info("已注册通知跳转协议：%s:// → %s", scheme, protocol_command())
        return True, ""
    except OSError as exc:
        logger.warning("注册 URL 协议失败：%s", exc)
        return False, str(exc)


def is_protocol_registered() -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        winreg = _winreg()
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, rf"{_CLASSES_KEY}\{config.PROTOCOL_SCHEME}\shell\open\command"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")
        return bool(value)
    except OSError:
        return False


def register_app_user_model_id(icon_path: str | None = None) -> tuple[bool, str]:
    """登记 AppUserModelId（Toast 通知的显示名称与图标）。"""
    if not _IS_WINDOWS:
        return False, "当前系统不是 Windows。"
    key_path = rf"{_CLASSES_KEY}\AppUserModelId\{config.APP_AUMID}"
    try:
        winreg = _winreg()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, config.APP_DISPLAY_NAME)
            winreg.SetValueEx(key, "ShowInSettings", 0, winreg.REG_DWORD, 1)
            if icon_path:
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon_path))
        return True, key_path
    except OSError as exc:
        logger.info("登记 AppUserModelId 失败：%s", exc)
        return False, str(exc)


def ensure_toast_registration(icon_path: str | None = None) -> tuple[bool, str]:
    """确保 Windows 接受本程序的通知。

    未打包的 Win32 程序要显示 Toast，需要两件事（微软文档要求）：

    1. 开始菜单里有一个 ``System.AppUserModel.ID`` 等于本程序 AUMID 的快捷方式；
    2. ``HKCU\\Software\\Classes\\AppUserModelId\\<AUMID>`` 里登记显示名称和图标。

    缺任何一项，``CreateToastNotifier`` 都会报错。全部失败时返回 (False, 原因)，
    调用方会退回托盘通知。
    """
    if not _IS_WINDOWS:
        return False, "当前系统不是 Windows。"
    from . import toast_registration

    if icon_path is None:
        try:
            from . import icons

            icon_path = icons.app_icon_path()
        except Exception:  # pragma: no cover - Qt 尚未初始化
            icon_path = None

    problems: list[str] = []
    aumid_ok, aumid_detail = register_app_user_model_id(icon_path)
    if not aumid_ok:
        problems.append(f"注册表登记失败：{aumid_detail}")

    shortcut_ok = False
    try:
        link = toast_registration.start_menu_programs_dir() / f"{config.APP_DISPLAY_NAME}.lnk"
        if link.exists():
            try:
                if toast_registration.read_shortcut_aumid(link) == config.APP_AUMID:
                    shortcut_ok = True
            except OSError:
                shortcut_ok = False
        if not shortcut_ok:
            exe, args = config.app_executable_and_args()
            shortcut_ok, detail = toast_registration.ensure_start_menu_shortcut(
                aumid=config.APP_AUMID,
                display_name=config.APP_DISPLAY_NAME,
                target=exe,
                arguments=args,
                icon=icon_path,
            )
            if not shortcut_ok:
                problems.append(f"创建开始菜单快捷方式失败：{detail}")
    except (OSError, ImportError) as exc:  # pragma: no cover - 依赖系统环境
        problems.append(str(exc))

    if aumid_ok and shortcut_ok:
        logger.info("系统通知身份已注册（%s）", config.APP_AUMID)
        return True, str(toast_registration.start_menu_programs_dir() / f"{config.APP_DISPLAY_NAME}.lnk")
    return False, "；".join(problems) or "未知原因"


# --------------------------------------------------------------------------
# 启动项辅助
# --------------------------------------------------------------------------
def open_folder(path: str | Path) -> tuple[bool, str]:
    target = str(path)
    try:
        if _IS_WINDOWS:
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True, ""
    except OSError as exc:
        return False, str(exc)


def play_notification_sound() -> None:
    """播放系统提示音（异步，不阻塞）。"""
    if not _IS_WINDOWS:
        return
    try:
        import winsound

        winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:  # pragma: no cover - 音频设备缺失时忽略
        pass


def open_url(url: str) -> bool:
    try:
        if _IS_WINDOWS:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
    except OSError:
        return False
    return False


def parse_protocol_url(url: str) -> tuple[str, str] | None:
    """解析 ``weeklyplanner://task/12`` 或 ``weeklyplanner://snooze/12``。"""
    if not url:
        return None
    text = url.strip().strip('"')
    prefix = f"{config.PROTOCOL_SCHEME}://"
    if not text.lower().startswith(prefix):
        return None
    rest = text[len(prefix):].strip("/")
    if not rest:
        return ("open", "")
    parts = rest.split("/")
    action = parts[0].lower()
    value = parts[1] if len(parts) > 1 else ""
    return (action, value)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
