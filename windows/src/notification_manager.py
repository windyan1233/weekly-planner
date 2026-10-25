"""通知管理：Windows 系统通知（Toast）+ 应用内浮窗 + 托盘气泡回退。

Windows 的 Toast 通过系统自带的 Windows PowerShell 5.1 调用 WinRT
``Windows.UI.Notifications`` 发出，属于真正的系统级通知：即使主窗口最小化到
托盘、被遮挡或应用内浮窗被关闭，也会出现在屏幕右下角 / 通知中心，并带有
「查看任务」「稍后提醒」两个按钮（通过注册的 URL 协议回到本程序）。

如果系统拒绝显示 Toast（例如某些精简版系统或未注册通知身份），会自动回退到
托盘气泡，并保证应用内浮窗始终可用。
"""

from __future__ import annotations

import html
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from . import config, windows_integration
from .logging_setup import get_logger
from .reminder_scheduler import ReminderMessage
from .settings_store import SettingsStore

logger = get_logger("notify")

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_POWERSHELL_AUMID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"

ToastSender = Callable[[ReminderMessage], "tuple[bool, str]"]


# --------------------------------------------------------------------------
# Toast 脚本
# --------------------------------------------------------------------------
def build_toast_xml(message: ReminderMessage) -> str:
    """生成 ToastGeneric 的 XML。"""
    escape = html.escape
    lines = [line for line in message.body.splitlines() if line.strip()]
    text_nodes = [f"<text>{escape(message.title)}</text>"]
    for line in lines[:3]:
        text_nodes.append(f"<text>{escape(line)}</text>")
    if not lines:
        text_nodes.append("<text></text>")

    actions = ""
    if message.task_id:
        actions = (
            '<actions>'
            f'<action content="查看任务" activationType="protocol"'
            f' arguments="{config.PROTOCOL_SCHEME}://task/{message.task_id}"/>'
            f'<action content="稍后提醒" activationType="protocol"'
            f' arguments="{config.PROTOCOL_SCHEME}://snooze/{message.reminder_id or message.task_id}"/>'
            "</actions>"
        )
    audio = '<audio src="ms-winsoundevent:Notification.Reminder"/>'
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<toast duration="long" activationType="protocol"'
        f' launch="{config.PROTOCOL_SCHEME}://task/{message.task_id}">'
        "<visual><binding template=\"ToastGeneric\">"
        + "".join(text_nodes)
        + "</binding></visual>"
        + actions
        + audio
        + "</toast>"
    )


_TOAST_SCRIPT_TEMPLATE = r"""# -*- coding: utf-8 -*-
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
} catch {
    Write-Output 'WINRT_UNAVAILABLE'
    exit 3
}
$xmlText = @'
__XML__
'@

function Show-Toast([string]$aumid) {
    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xmlText)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
    if ([string]::IsNullOrEmpty($aumid)) {
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier().Show($toast)
    } else {
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aumid).Show($toast)
    }
}

$lastError = ''
foreach ($aumid in @('__AUMID__', '__PS_AUMID__')) {
    try {
        Show-Toast $aumid
        Write-Output ('TOAST_OK ' + $aumid)
        exit 0
    } catch {
        $lastError = $_.Exception.Message
    }
}

# 最后一次尝试：给当前进程设置显式 AppUserModelID，再用无参 CreateToastNotifier
try {
    Add-Type -TypeDefinition 'using System;
using System.Runtime.InteropServices;
public class WpAumid {
    [DllImport("shell32.dll", PreserveSig = false)]
    public static extern void SetCurrentProcessExplicitAppUserModelID(
        [MarshalAs(UnmanagedType.LPWStr)] string id);
}' -ErrorAction Stop
    [WpAumid]::SetCurrentProcessExplicitAppUserModelID('__AUMID__')
    Show-Toast ''
    Write-Output 'TOAST_OK process-aumid'
    exit 0
} catch {
    $lastError = $_.Exception.Message
}

Write-Output ('TOAST_FAIL ' + $lastError)
exit 4
"""


def build_toast_script(xml_text: str) -> str:
    """生成用于显示 Toast 的 PowerShell 脚本。"""
    # 单引号 here-string 不支持转义单引号，先规避「行首 '@」这种边界
    safe_xml = xml_text.replace("\n'@", "\n''@")
    script = _TOAST_SCRIPT_TEMPLATE.replace("__XML__", safe_xml)
    script = script.replace("__PS_AUMID__", _POWERSHELL_AUMID)
    script = script.replace("__AUMID__", config.APP_AUMID.replace("'", "''"))
    return script


def powershell_path() -> Path | None:
    if sys.platform != "win32":
        return None
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if candidate.exists():
        return candidate
    return None


def send_windows_toast(message: ReminderMessage, *, timeout: float = 25.0) -> tuple[bool, str]:
    """调用 PowerShell 发出真实 Windows Toast。返回 (是否成功, 说明)。"""
    shell = powershell_path()
    if shell is None:
        return False, "未找到 Windows PowerShell，无法发送系统通知。"

    xml_text = build_toast_xml(message)
    script = build_toast_script(xml_text)

    script_path = None
    try:
        fd, script_path = tempfile.mkstemp(prefix="weekly_planner_toast_", suffix=".ps1")
        os.close(fd)
        # PowerShell 5.1 用 ANSI 读取无 BOM 文件，必须写入 UTF-8 BOM 才能正确显示中文
        Path(script_path).write_text(script, encoding="utf-8-sig")
        completed = subprocess.run(
            [
                str(shell),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                script_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, "调用系统通知超时。"
    except OSError as exc:
        return False, f"调用系统通知失败：{exc}"
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    if completed.returncode == 0 and "TOAST_OK" in output:
        return True, output
    detail = error or output or f"退出码 {completed.returncode}"
    logger.warning("系统通知发送失败：%s", detail)
    return False, detail


# --------------------------------------------------------------------------
# 管理器
# --------------------------------------------------------------------------
class NotificationManager(QObject):
    """把一条提醒同时投递到系统通知与应用内浮窗。"""

    popup_requested = Signal(object)      # ReminderMessage
    delivered = Signal(object, str)       # ReminderMessage, channel
    failed = Signal(str)
    _toast_result = Signal(object, bool, str)

    def __init__(
        self,
        settings: SettingsStore,
        *,
        parent: QObject | None = None,
        toast_sender: ToastSender | None = None,
        async_toast: bool = True,
        tray_icon_provider: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._toast_sender = toast_sender or send_windows_toast
        self._async_toast = async_toast
        self._tray_icon_provider = tray_icon_provider
        self._pending_lock = threading.Lock()
        self._inflight = 0
        self._toast_result.connect(self._on_toast_result)
        self._last_error = ""

    # ------------------------------------------------------------------
    @property
    def last_error(self) -> str:
        return self._last_error

    def set_tray_icon_provider(self, provider: Callable[[], object]) -> None:
        self._tray_icon_provider = provider

    def system_notification_enabled(self) -> bool:
        return self._settings.get_bool("system_notification") and sys.platform == "win32"

    # ------------------------------------------------------------------
    def notify(self, message: ReminderMessage) -> str:
        """发送通知，返回已使用的通道描述。"""
        channels: list[str] = []
        if self._settings.get_bool("notification_sound"):
            windows_integration.play_notification_sound()
        if self._settings.get_bool("inapp_notification"):
            self.popup_requested.emit(message)
            channels.append("inapp")

        if self.system_notification_enabled():
            self._dispatch_toast(message)
            channels.append("toast")
        else:
            self._fallback_tray(message)
            channels.append("tray")

        label = "+".join(channels) or "none"
        logger.info("通知已投递（%s）：%s", label, message.title)
        self.delivered.emit(message, label)
        return label

    def send_test(self) -> str:
        message = ReminderMessage(
            title="测试通知 · 一周日程",
            body="\n这是一条测试提醒，说明系统通知工作正常。\n你可以在设置里关闭系统通知。",
            task_id=0,
            reminder_id=None,
            kind="test",
        )
        return self.notify(message)

    # ------------------------------------------------------------------
    def _dispatch_toast(self, message: ReminderMessage) -> None:
        if self._async_toast:
            with self._pending_lock:
                self._inflight += 1
            thread = threading.Thread(
                target=self._toast_worker, args=(message,), daemon=True, name="toast"
            )
            thread.start()
        else:
            ok, detail = self._safe_send(message)
            self._on_toast_result(message, ok, detail)

    def _toast_worker(self, message: ReminderMessage) -> None:
        ok, detail = self._safe_send(message)
        self._toast_result.emit(message, ok, detail)

    def _safe_send(self, message: ReminderMessage) -> tuple[bool, str]:
        try:
            return self._toast_sender(message)
        except Exception as exc:  # pragma: no cover - 防御性
            logger.exception("发送系统通知时出现异常")
            return False, str(exc)

    def _on_toast_result(self, message: object, ok: bool, detail: str) -> None:
        with self._pending_lock:
            self._inflight = max(0, self._inflight - 1)
        if ok:
            self._last_error = ""
            return
        self._last_error = detail
        if isinstance(message, ReminderMessage):
            self._fallback_tray(message)
            self.failed.emit(f"系统通知不可用，已改用托盘气泡：{detail}")

    def _fallback_tray(self, message: ReminderMessage) -> None:
        icon = self._tray_icon_provider() if self._tray_icon_provider else None
        show = getattr(icon, "showMessage", None)
        if callable(show):
            try:
                from PySide6.QtWidgets import QSystemTrayIcon

                show(
                    message.title,
                    message.body.replace("\n", " "),
                    QSystemTrayIcon.MessageIcon.Information,
                    15000,
                )
            except Exception:  # pragma: no cover
                logger.exception("托盘气泡发送失败")
        else:
            logger.info("没有可用的托盘图标，仅保留应用内提醒")

    # ------------------------------------------------------------------
    def wait_for_toasts(self, timeout: float = 5.0) -> None:
        """测试辅助：等待后台 Toast 投递结束。"""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._pending_lock:
                if self._inflight <= 0:
                    return
            time.sleep(0.02)
