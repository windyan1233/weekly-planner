"""全局快捷键测试：组合解析、格式校验、注册与设置联动。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support import TestEnv, qapp  # noqa: E402

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from src.global_hotkey import (  # noqa: E402
    DEFAULT_HOTKEY,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    GlobalHotkey,
    HotkeyError,
    describe_error,
    is_available,
    normalize_combo,
    parse_hotkey,
)
from src.settings_dialog import SettingsDialog  # noqa: E402

VK_R = 0x52
VK_F8 = 0x77


class ParseTest(unittest.TestCase):
    def test_ctrl_shift_r(self) -> None:
        self.assertEqual(parse_hotkey("Ctrl+Shift+R"), (MOD_CONTROL | MOD_SHIFT, VK_R))

    def test_case_and_spaces_are_ignored(self) -> None:
        self.assertEqual(parse_hotkey(" ctrl + shift + r "), (MOD_CONTROL | MOD_SHIFT, VK_R))

    def test_function_key_without_modifier(self) -> None:
        self.assertEqual(parse_hotkey("F8"), (0, VK_F8))

    def test_single_letter_is_rejected(self) -> None:
        with self.assertRaises(HotkeyError):
            parse_hotkey("R")

    def test_missing_key_is_rejected(self) -> None:
        with self.assertRaises(HotkeyError):
            parse_hotkey("Ctrl+Shift")

    def test_two_keys_are_rejected(self) -> None:
        with self.assertRaises(HotkeyError):
            parse_hotkey("Ctrl+R+W")

    def test_empty_is_rejected(self) -> None:
        for text in ("", "   "):
            with self.assertRaises(HotkeyError):
                parse_hotkey(text)

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaises(HotkeyError):
            parse_hotkey("Ctrl+Shift+F25")

    def test_normalize_orders_modifiers(self) -> None:
        self.assertEqual(normalize_combo("shift+ctrl+r"), "Ctrl+Shift+R")
        self.assertEqual(normalize_combo("alt+f8"), "Alt+F8")

    def test_describe_error(self) -> None:
        self.assertIn("占用", describe_error(1409))
        self.assertIn("已生效", describe_error(0))
        self.assertIn("未知", describe_error(9999))
        self.assertIn("9999", describe_error(9999))

    def test_invalid_combo_returns_error(self) -> None:
        hotkey = GlobalHotkey()
        ok, error = hotkey.register("Ctrl+Shift")
        self.assertFalse(ok)
        self.assertEqual(error, -2)
        self.assertIn("未生效", hotkey.status_text())


class RegistrationTest(unittest.TestCase):
    """在真实 Windows 平台上注册/注销，验证 RegisterHotKey 的返回值处理。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qapp()

    def setUp(self) -> None:
        if not is_available() or QApplication.platformName() != "windows":
            self.skipTest("offscreen 平台没有真实窗口句柄，跳过真实注册测试")

    def test_register_and_unregister(self) -> None:
        hotkey = GlobalHotkey()
        ok, error = hotkey.register("Ctrl+Alt+Shift+F9")
        self.assertTrue(ok, describe_error(error))
        self.assertTrue(hotkey.is_registered())
        self.assertIn("已生效", hotkey.status_text())
        hotkey.unregister()
        self.assertFalse(hotkey.is_registered())
        self.assertEqual(hotkey.status_text(), "未启用")

    def test_duplicate_registration_reports_conflict(self) -> None:
        first = GlobalHotkey()
        ok, _ = first.register("Ctrl+Alt+Shift+F10")
        if not ok:
            self.skipTest("该组合在本机不可用，跳过")
        second = GlobalHotkey()
        # 不同窗口注册同一个组合，第二个应当报 1409
        ok2, error2 = second.register("Ctrl+Alt+Shift+F10")
        first.unregister()
        self.assertFalse(ok2)
        self.assertEqual(error2, 1409)


class FakeHotkeyManager:
    def __init__(self, result: tuple[bool, int] = (True, 0)) -> None:
        self.calls: list[str] = []
        self.registered = ""
        self.result = result
        self.error = 0

    def register(self, combo: str):
        self.calls.append(combo)
        ok, error = self.result
        if ok:
            self.registered = combo
            self.error = 0
        else:
            self.error = error
        return ok, error

    def unregister(self) -> None:
        self.registered = ""

    def clear_error(self) -> None:
        self.error = 0

    def is_registered(self) -> bool:
        return bool(self.registered)

    def status_text(self) -> str:
        if self.registered:
            return f"已生效：{self.registered}"
        return f"未生效：{describe_error(self.error)}" if self.error else "未启用"


class SettingsIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qapp()
        # 保存设置会尝试写开机启动注册表，测试里屏蔽掉，避免无权限时弹模态框
        cls._autostart_patch = patch(
            "src.settings_dialog.windows_integration.set_autostart",
            return_value=(True, ""),
        )
        cls._autostart_patch.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._autostart_patch.stop()

    def setUp(self) -> None:
        self.env = TestEnv("hotkey")
        self.manager = FakeHotkeyManager()
        self.env.settings.set("hotkey_enabled", True)
        self.env.settings.set("hotkey", DEFAULT_HOTKEY)

    def tearDown(self) -> None:
        self.env.close()

    def _dialog(self) -> SettingsDialog:
        return SettingsDialog(
            self.env.service,
            self.env.settings,
            None,
            hotkey_manager=self.manager,
        )

    def test_defaults_are_ctrl_shift_r(self) -> None:
        self.assertEqual(self.env.settings.get_str("hotkey"), "Ctrl+Shift+R")
        self.assertTrue(self.env.settings.get_bool("hotkey_enabled"))

    def test_dialog_shows_current_hotkey(self) -> None:
        dialog = self._dialog()
        self.assertTrue(dialog.hotkey_check.isChecked())
        self.assertEqual(dialog.hotkey_combo.currentText(), DEFAULT_HOTKEY)

    def test_save_new_hotkey(self) -> None:
        dialog = self._dialog()
        dialog.hotkey_combo.setCurrentText("Ctrl+Alt+F8")
        dialog._save()
        self.assertEqual(self.manager.calls[-1], "Ctrl+Alt+F8")
        self.assertEqual(self.env.settings.get_str("hotkey"), "Ctrl+Alt+F8")
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_save_disabled_unregisters(self) -> None:
        dialog = self._dialog()
        dialog.hotkey_check.setChecked(False)
        dialog._save()
        self.assertFalse(self.env.settings.get_bool("hotkey_enabled"))
        self.assertEqual(self.manager.registered, "")

    def test_conflict_keeps_dialog_open(self) -> None:
        self.manager.result = (False, 1409)
        dialog = self._dialog()
        dialog.hotkey_combo.setCurrentText("Ctrl+Alt+W")
        with patch("src.settings_dialog.QMessageBox.warning") as warning:
            dialog._save()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        # 未写入新组合
        self.assertEqual(self.env.settings.get_str("hotkey"), DEFAULT_HOTKEY)

    def test_invalid_combo_is_rejected(self) -> None:
        dialog = self._dialog()
        dialog.hotkey_combo.setCurrentText("Ctrl+Shift")
        with patch("src.settings_dialog.QMessageBox.warning") as warning:
            dialog._save()
        warning.assert_called_once()
        self.assertEqual(self.env.settings.get_str("hotkey"), DEFAULT_HOTKEY)

    def test_cancel_restores_original_registration(self) -> None:
        self.manager.registered = DEFAULT_HOTKEY  # 模拟程序当前已注册
        dialog = self._dialog()
        dialog.hotkey_combo.setCurrentText("Ctrl+Alt+F8")
        dialog._save()  # 先试注册新组合
        self.assertEqual(self.manager.registered, "Ctrl+Alt+F8")
        dialog2 = self._dialog()
        dialog2.hotkey_combo.setCurrentText("Ctrl+Shift+F8")
        dialog2.reject()
        self.assertEqual(self.manager.registered, "Ctrl+Alt+F8")


if __name__ == "__main__":
    unittest.main()
