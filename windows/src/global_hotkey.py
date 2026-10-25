"""全局快捷键（Windows RegisterHotKey）。

用途：程序最小化到托盘后，按一次 ``Ctrl+Shift+R`` 把窗口唤到前台。

实现要点
--------
* 用一个隐藏的 ``QWidget`` 作为消息窗口，``RegisterHotKey`` 注册后
  ``WM_HOTKEY`` 会进入它的窗口过程，由 ``nativeEvent`` 捕获。
* 注册失败（最常见的是错误码 1409「已被其它程序占用」）不会抛异常，
  而是返回 ``(False, 错误码)``，由界面提示用户换一个组合。
* 只支持 Windows；其它平台安全降级为「不可用」。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QWidget

WM_HOTKEY = 0x0312
HOTKEY_ID = 0xB10A
MOD_NOREPEAT = 0x4000

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

DEFAULT_HOTKEY = "Ctrl+Shift+R"
HOTKEY_PRESETS: tuple[str, ...] = (
    "Ctrl+Shift+R",
    "Ctrl+Alt+F8",
    "Ctrl+Shift+F8",
    "Ctrl+Alt+W",
    "Ctrl+Alt+P",
    "F8",
    "F9",
)

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}
_MODIFIER_LABELS = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))

_KEYS: dict[str, int] = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "`": 0xC0,
}
_KEY_LABELS = {
    0x20: "Space",
    0x0D: "Enter",
    0x09: "Tab",
    0x1B: "Esc",
    0x2D: "Insert",
    0x2E: "Delete",
    0x24: "Home",
    0x23: "End",
    0x21: "PageUp",
    0x22: "PageDown",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0xC0: "`",
}
for _letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _KEYS[_letter.lower()] = ord(_letter)
    _KEY_LABELS[ord(_letter)] = _letter
for _digit in "0123456789":
    _KEYS[_digit] = ord(_digit)
    _KEY_LABELS[ord(_digit)] = _digit
for _index in range(1, 25):
    _KEYS[f"f{_index}"] = 0x6F + _index
    _KEY_LABELS[0x6F + _index] = f"F{_index}"

_FUNCTION_KEY_RANGE = range(0x70, 0x88)


class HotkeyError(ValueError):
    """组合字符串不合法。"""


def normalize_combo(text: str) -> str:
    mods, vk = parse_hotkey(text)
    parts = [label for bit, label in _MODIFIER_LABELS if mods & bit]
    parts.append(_KEY_LABELS.get(vk, f"0x{vk:02X}"))
    return "+".join(parts)


def parse_hotkey(text: str) -> tuple[int, int]:
    """把 ``Ctrl+Shift+R`` 解析成 (修饰键位, 虚拟键码)。"""
    if not isinstance(text, str) or not text.strip():
        raise HotkeyError("快捷键不能为空。")
    tokens = [token for token in text.replace(" ", "").split("+") if token]
    if not tokens:
        raise HotkeyError("快捷键不能为空。")
    mods = 0
    key: int | None = None
    for token in tokens:
        lowered = token.lower()
        if lowered in _MODIFIERS:
            mods |= _MODIFIERS[lowered]
        elif lowered in _KEYS:
            if key is not None:
                raise HotkeyError("一个快捷键只能有一个主键。")
            key = _KEYS[lowered]
        else:
            raise HotkeyError(f"无法识别的按键：{token}")
    if key is None:
        raise HotkeyError("缺少主键，例如 Ctrl+Shift+R。")
    if mods == 0 and key not in _FUNCTION_KEY_RANGE:
        raise HotkeyError("单独的字母/数字会吞掉正常打字，请加上 Ctrl、Alt 或 Shift。")
    return mods, key


def describe_error(code: int) -> str:
    return {
        0: "已生效",
        5: "拒绝访问（可能被安全软件或权限设置阻止）",
        1400: "窗口句柄无效",
        1409: "已被其它程序占用",
        -1: "当前系统不支持全局快捷键",
        -2: "快捷键格式不正确",
    }.get(code, f"未知错误（错误码 {code}）")


def is_available() -> bool:
    return sys.platform == "win32"


class _HotkeyWindow(QWidget):
    """仅用于接收 WM_HOTKEY 的隐藏窗口。"""

    def __init__(self, owner: "GlobalHotkey") -> None:
        super().__init__(None)
        self._owner = owner
        self.setWindowTitle("WeeklyPlannerHotkeyWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.hide()

    def nativeEvent(self, event_type, message):  # noqa: N802 - Qt 接口
        if sys.platform == "win32":
            try:
                msg = wt.MSG.from_address(int(message))
            except (TypeError, ValueError, OSError):
                msg = None
            if msg is not None and msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID:
                self._owner._on_hotkey()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    """注册一个系统级快捷键，按下时发出 :attr:`activated`。"""

    activated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = _HotkeyWindow(self)
        self._registered = False
        self._combo = ""
        self._error = 0

    # ------------------------------------------------------------------
    @property
    def combo(self) -> str:
        return self._combo

    @property
    def error_code(self) -> int:
        return self._error

    def is_registered(self) -> bool:
        return self._registered

    def status_text(self) -> str:
        if self._registered:
            return f"已生效：{self._combo}"
        if self._error:
            return f"未生效：{describe_error(self._error)}"
        return "未启用"

    # ------------------------------------------------------------------
    def register(self, combo: str) -> tuple[bool, int]:
        """注册快捷键，返回 (是否成功, 错误码)。重复调用会先注销旧的。"""
        self.unregister()
        try:
            mods, vk = parse_hotkey(combo)
        except HotkeyError:
            self._error = -2
            return False, -2
        if not is_available():
            self._error = -1
            return False, -1

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.restype = wt.BOOL
        user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
        handle = int(self._window.winId())
        ctypes.set_last_error(0)
        ok = user32.RegisterHotKey(wt.HWND(handle), HOTKEY_ID, mods | MOD_NOREPEAT, vk)
        error = ctypes.get_last_error()
        if ok:
            self._registered = True
            self._combo = normalize_combo(combo)
            self._error = 0
            return True, 0
        self._registered = False
        self._error = error or -3
        return False, self._error

    def unregister(self) -> None:
        if self._registered and is_available():
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
                user32.UnregisterHotKey(wt.HWND(int(self._window.winId())), HOTKEY_ID)
            except OSError:
                pass
        self._registered = False
        self._combo = ""

    def clear_error(self) -> None:
        self._error = 0

    # ------------------------------------------------------------------
    def _on_hotkey(self) -> None:
        self.activated.emit()
