"""注册 Windows 通知身份（Start Menu 快捷方式 + AppUserModelID）。

Windows 的 Toast 通知要求「未打包」的桌面程序在开始菜单里有一个带有
``System.AppUserModel.ID`` 属性的快捷方式，否则
``ToastNotificationManager.CreateToastNotifier(aumid)`` 会报
“Element not found / no package identity”。

这里用 ctypes 调用 IShellLink + IPropertyStore 完成这件事，失败时返回
``(False, 原因)``，调用方可以安全地退回托盘通知。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import uuid
from pathlib import Path

from .logging_setup import get_logger

logger = get_logger("toast_reg")

HRESULT = ctypes.c_long
CLSCTX_INPROC_SERVER = 1

CLSID_SHELL_LINK = uuid.UUID("{00021401-0000-0000-C000-000000000046}")
IID_ISHELL_LINK_W = uuid.UUID("{000214F9-0000-0000-C000-000000000046}")
IID_IPROPERTY_STORE = uuid.UUID("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
IID_IPERSIST_FILE = uuid.UUID("{0000010B-0000-0000-C000-000000000046}")

FMTID_APP_USER_MODEL = uuid.UUID("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}")
PID_APP_USER_MODEL_ID = 5
PID_TOAST_ACTIVATOR = 26
VT_LPWSTR = 31


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", wt.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("r1", ctypes.c_ushort),
        ("r2", ctypes.c_ushort),
        ("r3", ctypes.c_ushort),
        ("pwszVal", ctypes.c_wchar_p),
        ("reserved", ctypes.c_void_p),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wt.DWORD),
        ("Data2", wt.WORD),
        ("Data3", wt.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: uuid.UUID) -> GUID:
    raw = value.bytes_le
    data4 = (ctypes.c_ubyte * 8)(*raw[8:])
    return GUID(
        int.from_bytes(raw[0:4], "little"),
        int.from_bytes(raw[4:6], "little"),
        int.from_bytes(raw[6:8], "little"),
        data4,
    )


def _is_available() -> bool:
    return sys.platform == "win32"


class _ComObject:
    def __init__(self, ptr: int) -> None:
        self._ptr = ptr

    def call(self, index: int, restype, *argtypes):
        vtable = ctypes.cast(
            self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        function = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])
        return function

    def query_interface(self, iid: uuid.UUID) -> int:
        func = self.call(0, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        ptr = ctypes.c_void_p()
        hr = func(self._ptr, ctypes.byref(_guid(iid)), ctypes.byref(ptr))
        if hr != 0 or not ptr.value:
            raise OSError(f"QueryInterface 失败：0x{hr & 0xFFFFFFFF:08X}")
        return ptr.value

    def release(self) -> None:
        if self._ptr:
            try:
                func = self.call(2, wt.ULONG)
                func(self._ptr)
            finally:
                self._ptr = 0


def _propertystore_set(store_ptr: int, pid: int, value: str) -> None:
    store = _ComObject(store_ptr)
    key = PROPERTYKEY()
    fmtid = _guid(FMTID_APP_USER_MODEL)
    ctypes.memmove(ctypes.byref(key.fmtid), ctypes.byref(fmtid), 16)
    key.pid = pid
    prop = PROPVARIANT()
    prop.vt = VT_LPWSTR
    prop.pwszVal = value
    set_value = store.call(
        6, HRESULT, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT)
    )
    hr = set_value(store_ptr, ctypes.byref(key), ctypes.byref(prop))
    if hr != 0:
        raise OSError(f"SetValue 失败：0x{hr & 0xFFFFFFFF:08X}")
    commit = store.call(7, HRESULT)
    hr = commit(store_ptr)
    if hr != 0:
        raise OSError(f"Commit 失败：0x{hr & 0xFFFFFFFF:08X}")


def _propertystore_get(store_ptr: int, pid: int) -> str:
    store = _ComObject(store_ptr)
    key = PROPERTYKEY()
    fmtid = _guid(FMTID_APP_USER_MODEL)
    ctypes.memmove(ctypes.byref(key.fmtid), ctypes.byref(fmtid), 16)
    key.pid = pid
    prop = PROPVARIANT()
    get_value = store.call(5, HRESULT, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
    hr = get_value(store_ptr, ctypes.byref(key), ctypes.byref(prop))
    if hr != 0:
        raise OSError(f"GetValue 失败：0x{hr & 0xFFFFFFFF:08X}")
    if prop.vt != VT_LPWSTR or not prop.pwszVal:
        raise OSError("属性不是字符串")
    return prop.pwszVal


def create_shortcut(
    link_path: str | Path,
    target: str | Path,
    *,
    arguments: str = "",
    icon: str | Path | None = None,
    aumid: str | None = None,
) -> Path:
    """创建带 AppUserModelID 的 .lnk（开始菜单快捷方式）。"""
    if not _is_available():
        raise OSError("仅支持 Windows")

    link_path = Path(link_path)
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists():
        try:
            link_path.unlink()
        except OSError:
            pass

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)

    clsid = _guid(CLSID_SHELL_LINK)
    iid_link = _guid(IID_ISHELL_LINK_W)
    ptr = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(clsid),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(iid_link),
        ctypes.byref(ptr),
    )
    if hr != 0 or not ptr.value:
        raise OSError(f"无法创建 IShellLink：0x{hr & 0xFFFFFFFF:08X}")

    link = _ComObject(ptr.value)
    store = None
    persist = None
    try:
        set_path = link.call(20, HRESULT, ctypes.c_wchar_p)
        hr = set_path(link._ptr, str(target))
        if hr != 0:
            raise OSError(f"SetPath 失败：0x{hr & 0xFFFFFFFF:08X}")
        if arguments:
            set_args = link.call(11, HRESULT, ctypes.c_wchar_p)
            set_args(link._ptr, arguments)
        icon_path = str(icon or target)
        set_icon = link.call(17, HRESULT, ctypes.c_wchar_p, ctypes.c_int)
        set_icon(link._ptr, icon_path, 0)
        # 工作目录固定为程序所在目录，避免从开始菜单启动时继承到奇怪的当前目录
        set_dir = link.call(9, HRESULT, ctypes.c_wchar_p)
        set_dir(link._ptr, str(Path(target).parent))

        if aumid:
            store_ptr = link.query_interface(IID_IPROPERTY_STORE)
            store = _ComObject(store_ptr)
            _propertystore_set(store_ptr, PID_APP_USER_MODEL_ID, aumid)

        persist_ptr = link.query_interface(IID_IPERSIST_FILE)
        persist = _ComObject(persist_ptr)
        save = persist.call(6, HRESULT, ctypes.c_wchar_p, ctypes.c_int)
        hr = save(persist_ptr, str(link_path), 1)
        if hr != 0:
            raise OSError(f"保存快捷方式失败：0x{hr & 0xFFFFFFFF:08X}")
    finally:
        if persist is not None:
            persist.release()
        if store is not None:
            store.release()
        link.release()
        ole32.CoUninitialize()

    if not link_path.exists():
        raise OSError("快捷方式没有生成")
    return link_path


def read_shortcut_aumid(link_path: str | Path) -> str:
    """读取 .lnk 的 AppUserModelID（用于自检）。"""
    if not _is_available():
        raise OSError("仅支持 Windows")
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    try:
        clsid = _guid(CLSID_SHELL_LINK)
        iid_link = _guid(IID_ISHELL_LINK_W)
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(iid_link), ctypes.byref(ptr),
        )
        if hr != 0 or not ptr.value:
            raise OSError(f"无法创建 IShellLink：0x{hr & 0xFFFFFFFF:08X}")
        link = _ComObject(ptr.value)
        persist = None
        store = None
        try:
            persist_ptr = link.query_interface(IID_IPERSIST_FILE)
            persist = _ComObject(persist_ptr)
            load = persist.call(5, HRESULT, ctypes.c_wchar_p, ctypes.c_int)
            hr = load(persist_ptr, str(link_path), 0)
            if hr != 0:
                raise OSError(f"加载快捷方式失败：0x{hr & 0xFFFFFFFF:08X}")
            store_ptr = link.query_interface(IID_IPROPERTY_STORE)
            store = _ComObject(store_ptr)
            return _propertystore_get(store_ptr, PID_APP_USER_MODEL_ID)
        finally:
            if store is not None:
                store.release()
            if persist is not None:
                persist.release()
            link.release()
    finally:
        ole32.CoUninitialize()


def start_menu_programs_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def ensure_start_menu_shortcut(
    *,
    aumid: str,
    display_name: str,
    target: str | Path,
    arguments: str = "",
    icon: str | Path | None = None,
) -> tuple[bool, str]:
    """确保开始菜单里有带 AUMID 的快捷方式（Toast 通知的注册依据）。"""
    if not _is_available():
        return False, "仅支持 Windows"
    link_path = start_menu_programs_dir() / f"{display_name}.lnk"
    try:
        create_shortcut(
            link_path,
            target,
            arguments=arguments,
            icon=icon,
            aumid=aumid,
        )
        return True, str(link_path)
    except (OSError, AttributeError) as exc:
        logger.info("创建通知快捷方式失败：%s", exc)
        return False, str(exc)


def shortcut_exists(display_name: str) -> bool:
    return (start_menu_programs_dir() / f"{display_name}.lnk").exists()
