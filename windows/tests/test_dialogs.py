"""对话框测试：真正操作界面控件，验证「一个任务多个计划时间」的完整流程。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support import TestEnv, qapp  # noqa: E402

from PySide6.QtCore import QDate, QTime  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

from src.models import PlanDraft  # noqa: E402
from src.settings_dialog import SettingsDialog  # noqa: E402
from src.task_dialog import PlanEditDialog, TaskDetailDialog, TaskDialog  # noqa: E402
from src.theme import ThemeManager  # noqa: E402
from src.windows_integration import parse_protocol_url  # noqa: E402


class TaskDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qapp()

    def setUp(self) -> None:
        self.env = TestEnv("dialog")
        self.theme = ThemeManager(self.app)
        self.theme.apply("light")

    def tearDown(self) -> None:
        self.env.close()

    def _fill_due(self, dialog: TaskDialog, year: int, month: int, day: int, hour: int, minute: int) -> None:
        dialog.due_date_edit.setDate(QDate(year, month, day))
        dialog.due_time_edit.setTime(QTime(hour, minute))

    def test_create_task_with_multiple_plan_times(self) -> None:
        dialog = TaskDialog(self.env.service)
        dialog.title_edit.setText("完成课程报告")
        dialog.description_edit.setPlainText("12 页，附参考文献")
        dialog.category_combo.setCurrentText("学习")
        for button in dialog.priority_group.buttons():
            if button.property("priority") == "important":
                button.setChecked(True)
        self._fill_due(dialog, 2026, 10, 25, 18, 0)
        dialog._add_plan_row(
            PlanDraft(
                plan_at=datetime(2026, 10, 20, 19, 0),
                label="收集资料",
                remind_enabled=True,
                remind_lead_minutes=10,
            )
        )
        dialog._add_plan_row(PlanDraft(plan_at=datetime(2026, 10, 22, 20, 0), label="完成初稿"))
        dialog._add_plan_row(PlanDraft(plan_at=datetime(2026, 10, 24, 15, 0), label="检查修改"))
        self.assertEqual(len(dialog._plan_rows), 3)

        dialog._save()

        self.assertIsNotNone(dialog.saved_task_id)
        task = self.env.service.get_task(int(dialog.saved_task_id or 0))
        self.assertEqual(task.title, "完成课程报告")
        self.assertEqual(task.description, "12 页，附参考文献")
        self.assertEqual(task.due_at, datetime(2026, 10, 25, 18, 0))
        self.assertEqual(task.priority, "important")
        self.assertEqual(len(task.plans), 3)
        self.assertEqual([p.label for p in task.sorted_plans()], ["收集资料", "完成初稿", "检查修改"])
        first = task.sorted_plans()[0]
        self.assertTrue(first.remind_enabled)
        self.assertEqual(first.remind_lead_minutes, 10)
        # 截止提醒 + 第一个计划时间的提醒
        self.assertEqual(len(self.env.reminder_rows(int(task.id or 0))), 2)

    def test_title_is_required_and_dialog_stays_open(self) -> None:
        dialog = TaskDialog(self.env.service)
        dialog.title_edit.setText("   ")
        dialog._save()
        self.assertIsNone(dialog.saved_task_id)
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(dialog.error_label.isVisibleTo(dialog) or dialog.error_label.text())
        self.assertEqual(self.env.task_count(), 0)

    def test_initial_plan_prefill_from_week_view_click(self) -> None:
        slot = datetime(2026, 10, 21, 14, 0)
        dialog = TaskDialog(self.env.service, initial_plan=slot, initial_due=slot + timedelta(hours=3))
        self.assertEqual(len(dialog._plan_rows), 1)
        self.assertEqual(dialog._plan_rows[0].to_draft().plan_at, slot)
        dialog.title_edit.setText("从时间格创建")
        dialog._save()
        task = self.env.service.get_task(int(dialog.saved_task_id or 0))
        self.assertEqual(len(task.plans), 1)
        self.assertEqual(task.plans[0].plan_at, slot)

    def test_edit_removes_only_one_plan_time(self) -> None:
        task_id = self.env.create_task(
            title="多计划任务",
            due_at=datetime(2026, 10, 25, 18, 0),
            plans=[
                PlanDraft(plan_at=datetime(2026, 10, 20, 19, 0), label="A"),
                PlanDraft(plan_at=datetime(2026, 10, 22, 20, 0), label="B"),
            ],
        )
        task = self.env.service.get_task(task_id)
        dialog = TaskDialog(self.env.service, task=task)
        self.assertEqual(len(dialog._plan_rows), 2)
        dialog._remove_plan_row(dialog._plan_rows[0])
        self.assertEqual(len(dialog._plan_rows), 1)
        dialog._save()

        updated = self.env.service.get_task(task_id)
        self.assertEqual(updated.title, "多计划任务")
        self.assertEqual(len(updated.plans), 1)
        self.assertEqual(updated.plans[0].label, "B")

    def test_edit_changes_due_time(self) -> None:
        task_id = self.env.create_task(title="改期", due_at=datetime(2026, 10, 20, 12, 0))
        task = self.env.service.get_task(task_id)
        dialog = TaskDialog(self.env.service, task=task)
        self._fill_due(dialog, 2026, 10, 23, 9, 30)
        dialog._save()
        updated = self.env.service.get_task(task_id)
        self.assertEqual(updated.due_at, datetime(2026, 10, 23, 9, 30))

    def test_plan_edit_dialog(self) -> None:
        task_id = self.env.create_task(
            title="单独编辑计划时间",
            due_at=datetime(2026, 10, 25, 18, 0),
            plans=[PlanDraft(plan_at=datetime(2026, 10, 20, 19, 0), label="原本")],
        )
        plan = self.env.service.get_task(task_id).plans[0]
        dialog = PlanEditDialog(self.env.service, plan)
        dialog.date_edit.setDate(QDate(2026, 10, 21))
        dialog.time_edit.setTime(QTime(8, 45))
        dialog.label_edit.setText("改过的说明")
        dialog.remind_combo.setCurrentIndex(3)  # 提前 15 分钟
        dialog._save()
        updated = self.env.service.get_task(task_id)
        self.assertEqual(len(updated.plans), 1)
        self.assertEqual(updated.plans[0].plan_at, datetime(2026, 10, 21, 8, 45))
        self.assertEqual(updated.plans[0].label, "改过的说明")
        self.assertTrue(updated.plans[0].remind_enabled)
        self.assertEqual(updated.plans[0].remind_lead_minutes, 15)


    def test_plan_row_with_end_time_and_three_reminder_switches(self) -> None:
        dialog = TaskDialog(self.env.service)
        dialog.title_edit.setText("带结束时间的任务")
        self._fill_due(dialog, 2026, 10, 25, 18, 0)
        dialog._add_plan_row(PlanDraft(plan_at=datetime(2026, 10, 20, 22, 0)))
        row = dialog._plan_rows[0]
        self.assertFalse(row.has_end)
        self.assertFalse(row.remind_end_checkbox.isVisibleTo(row))
        self.assertFalse(row.remind_start_checkbox.isChecked())

        row.end_checkbox.setChecked(True)
        self.assertTrue(row.has_end)
        self.assertTrue(row.remind_end_checkbox.isVisibleTo(row))
        # 打开结束时间时默认「开始后 1 小时」
        self.assertEqual(row.to_draft().end_at, datetime(2026, 10, 20, 23, 0))

        # 改成跨天：10-20 22:00 → 10-22 09:30
        row.end_date_edit.setDate(QDate(2026, 10, 22))
        row.end_time_edit.setTime(QTime(9, 30))
        row.remind_start_checkbox.setChecked(True)  # 打开后自动选中「提前 10 分钟」
        row.remind_end_checkbox.setChecked(True)
        self.assertEqual(row.validation_error(), "")
        draft = row.to_draft()
        self.assertEqual(draft.end_at, datetime(2026, 10, 22, 9, 30))
        self.assertTrue(draft.remind_start)
        self.assertEqual(draft.remind_lead_minutes, 10)
        self.assertTrue(draft.remind_end)

        dialog._save()
        task = self.env.service.get_task(int(dialog.saved_task_id or 0))
        plan = task.plans[0]
        self.assertEqual(plan.end_at, datetime(2026, 10, 22, 9, 30))
        self.assertTrue(plan.remind_start)
        self.assertTrue(plan.remind_end)
        kinds = {row.kind for row in self.env.reminder_rows(int(task.id or 0))}
        self.assertEqual(kinds, {"due", "plan", "plan_end"})

    def test_dialog_rejects_end_before_start(self) -> None:
        dialog = TaskDialog(self.env.service)
        dialog.title_edit.setText("结束早于开始")
        self._fill_due(dialog, 2026, 10, 25, 18, 0)
        dialog._add_plan_row(
            PlanDraft(
                plan_at=datetime(2026, 10, 20, 22, 0),
                end_at=datetime(2026, 10, 20, 21, 0),
            )
        )
        row = dialog._plan_rows[0]
        self.assertEqual(row.validation_error(), "计划的结束时间必须晚于开始时间。")
        dialog._save()
        self.assertIsNone(dialog.saved_task_id)
        self.assertIn("结束时间", dialog.error_label.text())
        self.assertEqual(self.env.task_count(), 0)

    def test_editing_existing_plan_shows_end_and_switches(self) -> None:
        end = datetime(2026, 10, 22, 9, 30)
        task_id = self.env.create_task(
            title="已有跨天计划",
            due_at=datetime(2026, 10, 25, 18, 0),
            plans=[
                PlanDraft(
                    plan_at=datetime(2026, 10, 20, 22, 0),
                    end_at=end,
                    remind_start=True,
                    remind_end=True,
                )
            ],
        )
        task = self.env.service.get_task(task_id)
        dialog = TaskDialog(self.env.service, task=task)
        row = dialog._plan_rows[0]
        self.assertTrue(row.end_checkbox.isChecked())
        self.assertTrue(row.remind_start_checkbox.isChecked())
        self.assertTrue(row.remind_end_checkbox.isChecked())
        self.assertEqual(row.to_draft().end_at, end)

        # 关闭结束时间后保存：end_at 被清空，结束提醒也随之关闭
        row.end_checkbox.setChecked(False)
        dialog._save()
        plan = self.env.service.get_task(task_id).plans[0]
        self.assertIsNone(plan.end_at)
        self.assertFalse(plan.remind_end)
        self.assertTrue(plan.remind_start)
        self.assertNotIn("plan_end", {r.kind for r in self.env.reminder_rows(task_id)})

    def test_due_reminder_switch_defaults_on(self) -> None:
        dialog = TaskDialog(self.env.service)
        self.assertEqual(dialog.remind_checkbox.text(), "提醒截止")
        self.assertTrue(dialog.remind_checkbox.isChecked())

    def test_plan_edit_dialog_can_set_end_time(self) -> None:
        task_id = self.env.create_task(
            title="单独编辑结束时间",
            due_at=datetime(2026, 10, 25, 18, 0),
            plans=[PlanDraft(plan_at=datetime(2026, 10, 20, 19, 0), label="原本")],
        )
        plan = self.env.service.get_task(task_id).plans[0]
        dialog = PlanEditDialog(self.env.service, plan)
        self.assertFalse(dialog.end_checkbox.isChecked())
        dialog.end_checkbox.setChecked(True)
        dialog.end_date_edit.setDate(QDate(2026, 10, 21))
        dialog.end_time_edit.setTime(QTime(8, 45))
        dialog.remind_combo.setCurrentIndex(3)  # 提前 15 分钟
        dialog.remind_end_checkbox.setChecked(True)
        dialog._save()

        updated = self.env.service.get_task(task_id).plans[0]
        self.assertEqual(updated.end_at, datetime(2026, 10, 21, 8, 45))
        self.assertTrue(updated.remind_start)
        self.assertEqual(updated.remind_lead_minutes, 15)
        self.assertTrue(updated.remind_end)


class TaskDetailDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        qapp()

    def setUp(self) -> None:
        self.env = TestEnv("detail")
        self.task_id = self.env.create_task(
            title="详情任务",
            due_at=datetime.now() + timedelta(days=2),
            plans=[
                PlanDraft(plan_at=datetime.now() + timedelta(days=1), label="第一步", remind_enabled=True),
                PlanDraft(plan_at=datetime.now() + timedelta(days=2), label="第二步"),
            ],
        )

    def tearDown(self) -> None:
        self.env.close()

    def test_detail_dialog_shows_task_and_toggles_plan(self) -> None:
        dialog = TaskDetailDialog(self.env.service, self.task_id)
        self.assertEqual(dialog.windowTitle(), "任务详情")
        task = dialog._task()
        self.assertEqual(task.title, "详情任务")
        self.assertEqual(len(task.plans), 2)

        plan = task.sorted_plans()[0]
        dialog._set_plan_done(plan, True)
        refreshed = self.env.service.get_task(self.task_id)
        done_plan = next(p for p in refreshed.plans if p.id == plan.id)
        self.assertTrue(done_plan.done)

    def test_detail_toggle_task_done(self) -> None:
        dialog = TaskDetailDialog(self.env.service, self.task_id)
        dialog._toggle_done()
        self.assertEqual(self.env.service.get_task(self.task_id).status, "done")
        dialog._toggle_done()
        self.assertEqual(self.env.service.get_task(self.task_id).status, "todo")

    def test_detail_shows_cross_day_range_and_end_reminder(self) -> None:
        from PySide6.QtWidgets import QLabel

        task_id = self.env.create_task(
            title="详情里的跨天计划",
            due_at=datetime(2026, 10, 25, 18, 0),
            plans=[
                PlanDraft(
                    plan_at=datetime(2026, 10, 20, 22, 0),
                    end_at=datetime(2026, 10, 22, 9, 30),
                    remind_start=True,
                    remind_end=True,
                )
            ],
        )
        dialog = TaskDetailDialog(self.env.service, task_id)
        texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn("10-20 22:00 → 10-22 09:30", texts)
        self.assertIn("跨3天", texts)
        self.assertIn("结束提醒", texts)


class SettingsDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qapp()
        # 设置窗口保存时会尝试写开机启动注册表；测试里不要碰真实系统状态，
        # 否则无权限时会弹出模态提示框把测试挂住
        cls._autostart_patch = patch(
            "src.settings_dialog.windows_integration.set_autostart",
            return_value=(True, ""),
        )
        cls._autostart_patch.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._autostart_patch.stop()

    def setUp(self) -> None:
        self.env = TestEnv("settings")
        self.theme = ThemeManager(self.app)
        self.theme.apply("light")

    def tearDown(self) -> None:
        self.theme.apply("light")
        self.env.close()

    def test_settings_dialog_reflects_and_saves_values(self) -> None:
        self.env.settings.set("missed_grace_hours", 24)
        dialog = SettingsDialog(
            self.env.service, self.env.settings, self.env.engine, theme_manager=self.theme
        )
        self.assertEqual(dialog.grace_spin.value(), 24)
        self.assertEqual(dialog.mode_combo.currentData(), "before_due_24h")

        dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("previous_day_at"))
        dialog.previous_day_edit.setTime(QTime(8, 30))
        dialog.grace_spin.setValue(6)
        dialog.snooze_spin.setValue(20)
        dialog._save()

        self.assertEqual(self.env.settings.get_str("theme"), "dark")
        self.assertEqual(self.env.settings.get_str("reminder_mode"), "previous_day_at")
        self.assertEqual(self.env.settings.get_str("previous_day_time"), "08:30")
        self.assertEqual(self.env.settings.get_int("missed_grace_hours"), 6)
        self.assertEqual(self.env.settings.snooze_minutes(), 20)
        self.assertEqual(self.theme.resolved, "dark")

    def test_previous_day_time_disabled_for_24h_mode(self) -> None:
        dialog = SettingsDialog(self.env.service, self.env.settings, self.env.engine)
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("before_due_24h"))
        self.assertFalse(dialog.previous_day_edit.isEnabled())
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("previous_day_at"))
        self.assertTrue(dialog.previous_day_edit.isEnabled())

    def test_cancel_restores_theme(self) -> None:
        dialog = SettingsDialog(
            self.env.service, self.env.settings, self.env.engine, theme_manager=self.theme
        )
        dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
        dialog._apply_theme_preview()
        self.assertEqual(self.theme.resolved, "dark")
        dialog.reject()
        self.assertEqual(self.theme.resolved, "light")
        self.assertEqual(self.env.settings.get_str("theme"), "light")


class ProtocolUrlTest(unittest.TestCase):
    def test_task_url(self) -> None:
        self.assertEqual(parse_protocol_url("weeklyplanner://task/42"), ("task", "42"))

    def test_snooze_url(self) -> None:
        self.assertEqual(parse_protocol_url("weeklyplanner://snooze/7"), ("snooze", "7"))

    def test_plain_open(self) -> None:
        self.assertEqual(parse_protocol_url("weeklyplanner://"), ("open", ""))

    def test_other_scheme_is_none(self) -> None:
        self.assertIsNone(parse_protocol_url("https://example.com"))
        self.assertIsNone(parse_protocol_url(""))

    def test_quoted_argument(self) -> None:
        self.assertEqual(parse_protocol_url('"weeklyplanner://task/9"'), ("task", "9"))


if __name__ == "__main__":
    unittest.main()
