"""周视图测试：周一~周日边界、跨月跨年、日期变化、重叠排布、跨天绘制、界面集成。"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support import TestEnv, qapp  # noqa: E402

from src.models import Occurrence, PlanDraft, PlanTime, Task  # noqa: E402
from src.theme import LIGHT, ThemeManager  # noqa: E402
from src.time_utils import (  # noqa: E402
    covered_dates,
    plan_range_label,
    start_of_week,
    week_bounds,
    week_days,
    week_number,
    week_range_label,
)
from src.weekly_calendar import (  # noqa: E402
    CONTINUATION_AT_MINUTES,
    CONTINUATION_HEIGHT,
    HOUR_HEIGHT,
    COLUMN_PAD_Y,
    EventChip,
    WeekView,
    assign_lanes,
    build_day_segments,
)


class WeekMathTest(unittest.TestCase):
    def test_week_starts_on_monday(self) -> None:
        # 2026-10-14 是周三
        self.assertEqual(start_of_week(date(2026, 10, 14)), date(2026, 10, 12))
        self.assertEqual(start_of_week(datetime(2026, 10, 18, 23, 59)), date(2026, 10, 12))

    def test_week_bounds_monday_to_sunday(self) -> None:
        start, end = week_bounds(date(2026, 10, 14))
        self.assertEqual(start, date(2026, 10, 12))
        self.assertEqual(end, date(2026, 10, 18))
        self.assertEqual(end.weekday(), 6)

    def test_week_days_are_seven_in_order(self) -> None:
        days = week_days(date(2026, 10, 14))
        self.assertEqual(len(days), 7)
        self.assertEqual([day.weekday() for day in days], list(range(7)))

    def test_sunday_to_monday_switch(self) -> None:
        sunday = date(2026, 10, 18)
        monday = date(2026, 10, 19)
        self.assertNotEqual(start_of_week(sunday), start_of_week(monday))
        self.assertEqual(start_of_week(monday), start_of_week(sunday) + timedelta(days=7))

    def test_month_end_and_year_end(self) -> None:
        # 2026-10-31 是周六，所在周跨 10 月与 11 月
        start, end = week_bounds(date(2026, 10, 31))
        self.assertEqual(start, date(2026, 10, 26))
        self.assertEqual(end, date(2026, 11, 1))
        self.assertIn("10月26日", week_range_label(start, end))
        self.assertIn("11月1日", week_range_label(start, end))

        # 2025-12-31 是周三，所在周跨年
        start, end = week_bounds(date(2025, 12, 31))
        self.assertEqual(start, date(2025, 12, 29))
        self.assertEqual(end, date(2026, 1, 4))
        self.assertIn("2025年", week_range_label(start, end))
        self.assertIn("2026年", week_range_label(start, end))
        self.assertEqual(start_of_week(date(2026, 1, 1)), date(2025, 12, 29))

    def test_week_number(self) -> None:
        self.assertEqual(week_number(date(2026, 10, 14)), 42)


def make_occurrence(
    *,
    day: date,
    hour: int,
    minute: int = 0,
    kind: str = "plan",
    task_id: int = 1,
    title: str = "任务",
    plan_id: int = 1,
    duration: int = 45,
    plan_index: int = 1,
    plan_total: int = 1,
    priority: str = "normal",
    end_at: datetime | None = None,
) -> Occurrence:
    start = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    plan = (
        PlanTime(id=plan_id, task_id=task_id, plan_at=start, end_at=end_at)
        if kind == "plan"
        else None
    )
    task = Task(
        id=task_id,
        title=title,
        due_at=start + timedelta(days=2),
        priority=priority,
        plans=[plan] if plan else [],
    )
    return Occurrence(
        task_id=task_id,
        title=title,
        kind=kind,
        start=start,
        task=task,
        plan=plan,
        plan_index=plan_index,
        plan_total=plan_total,
        duration_minutes=duration,
        end_at=end_at,
    )


def make_cross_day_occurrence(
    *,
    start_day: date = date(2026, 10, 20),
    start_hour: int = 22,
    end_day: date = date(2026, 10, 22),
    end_hour: int = 9,
    end_minute: int = 30,
    task_id: int = 1,
) -> Occurrence:
    start = datetime.combine(start_day, time(start_hour, 0))
    end = datetime.combine(end_day, time(end_hour, end_minute))
    plan = PlanTime(
        id=1, task_id=task_id, plan_at=start, end_at=end, remind_start=True, remind_end=True
    )
    task = Task(
        id=task_id,
        title="跨天任务",
        due_at=end + timedelta(days=2),
        plans=[plan],
    )
    return Occurrence(
        task_id=task_id,
        title="跨天任务",
        kind="plan",
        start=start,
        task=task,
        plan=plan,
        plan_index=1,
        plan_total=1,
        duration_minutes=int((end - start).total_seconds() // 60),
        end_at=end,
    )


class PlanRangeLabelTest(unittest.TestCase):
    """列表 / 任务描述里的计划时间文本（纯函数）。"""

    def test_legacy_plan_without_end_keeps_short_format(self) -> None:
        start = datetime(2026, 10, 20, 19, 0)
        self.assertEqual(plan_range_label(start), "19:00")
        self.assertEqual(plan_range_label(start, None), "19:00")

    def test_same_day_range(self) -> None:
        start = datetime(2026, 10, 20, 9, 0)
        end = datetime(2026, 10, 20, 10, 30)
        self.assertEqual(plan_range_label(start, end), "09:00-10:30")

    def test_cross_day_range_shows_dates_and_span(self) -> None:
        start = datetime(2026, 10, 20, 22, 0)
        end = datetime(2026, 10, 22, 9, 30)
        self.assertEqual(plan_range_label(start, end), "10-20 22:00 → 10-22 09:30 · 跨3天")

    def test_cross_day_span_counts_calendar_days(self) -> None:
        # 10-20 → 10-21 只跨 2 天；跨月也按自然日计算
        two = plan_range_label(datetime(2026, 10, 20, 23, 0), datetime(2026, 10, 21, 1, 0))
        self.assertIn("跨2天", two)
        across_month = plan_range_label(
            datetime(2026, 10, 31, 22, 0), datetime(2026, 11, 1, 2, 0)
        )
        self.assertEqual(across_month, "10-31 22:00 → 11-01 02:00 · 跨2天")

    def test_covered_dates(self) -> None:
        start = datetime(2026, 10, 20, 22, 0)
        end = datetime(2026, 10, 22, 9, 30)
        self.assertEqual(
            covered_dates(start, end),
            [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)],
        )
        # 没有结束时间 / 同一天都只覆盖一天
        self.assertEqual(covered_dates(start), [date(2026, 10, 20)])
        self.assertEqual(covered_dates(start, datetime(2026, 10, 20, 23, 0)), [date(2026, 10, 20)])

    def test_occurrence_detail_text_uses_range(self) -> None:
        cross = make_cross_day_occurrence()
        self.assertIn("10-20 22:00 → 10-22 09:30", cross.detail_text)
        self.assertIn("跨3天", cross.detail_text)
        self.assertIn("结束提醒", cross.detail_text)
        self.assertTrue(cross.is_cross_day)
        self.assertEqual(cross.span_days, 3)

        legacy = make_occurrence(day=date(2026, 10, 14), hour=9)
        self.assertEqual(legacy.detail_text.split(" · ")[0], "计划 09:00")
        self.assertFalse(legacy.is_cross_day)


class DaySegmentsTest(unittest.TestCase):
    """把跨天计划按天裁剪成绘制片段（纯函数）。"""

    def setUp(self) -> None:
        self.occ = make_cross_day_occurrence()

    def test_same_day_plan_uses_real_end_time(self) -> None:
        occ = make_occurrence(
            day=date(2026, 10, 14),
            hour=9,
            duration=120,
            end_at=datetime(2026, 10, 14, 11, 0),
        )
        segments = build_day_segments([occ], date(2026, 10, 14))
        self.assertEqual(len(segments), 1)
        self.assertEqual((segments[0].start_minutes, segments[0].end_minutes), (9 * 60, 11 * 60))
        self.assertFalse(segments[0].continuation)
        self.assertEqual(build_day_segments([occ], date(2026, 10, 15)), [])

    def test_start_day_is_drawn_until_23(self) -> None:
        segments = build_day_segments([self.occ], date(2026, 10, 20))
        self.assertEqual(len(segments), 1)
        self.assertFalse(segments[0].continuation)
        self.assertEqual((segments[0].start_minutes, segments[0].end_minutes), (22 * 60, 23 * 60))

    def test_middle_day_is_a_continuation_bar(self) -> None:
        segments = build_day_segments([self.occ], date(2026, 10, 21))
        self.assertEqual(len(segments), 1)
        self.assertTrue(segments[0].continuation)
        self.assertEqual(segments[0].start_minutes, CONTINUATION_AT_MINUTES)

    def test_end_day_is_drawn_from_7(self) -> None:
        segments = build_day_segments([self.occ], date(2026, 10, 22))
        self.assertEqual(len(segments), 1)
        self.assertFalse(segments[0].continuation)
        self.assertEqual((segments[0].start_minutes, segments[0].end_minutes), (7 * 60, 9 * 60 + 30))

    def test_days_outside_the_span_are_skipped(self) -> None:
        self.assertEqual(build_day_segments([self.occ], date(2026, 10, 19)), [])
        self.assertEqual(build_day_segments([self.occ], date(2026, 10, 23)), [])

    def test_end_before_7am_falls_back_to_midnight(self) -> None:
        occ = make_cross_day_occurrence(
            start_day=date(2026, 10, 20),
            start_hour=22,
            end_day=date(2026, 10, 21),
            end_hour=2,
            end_minute=0,
        )
        segments = build_day_segments([occ], date(2026, 10, 21))
        self.assertEqual(len(segments), 1)
        self.assertEqual((segments[0].start_minutes, segments[0].end_minutes), (0, 2 * 60))

    def test_legacy_plan_keeps_fixed_duration(self) -> None:
        occ = make_occurrence(day=date(2026, 10, 14), hour=9, duration=45)
        segments = build_day_segments([occ], date(2026, 10, 14))
        self.assertEqual(len(segments), 1)
        self.assertEqual((segments[0].start_minutes, segments[0].end_minutes), (9 * 60, 9 * 60 + 45))


class LaneLayoutTest(unittest.TestCase):
    def test_disjoint_items_single_lane(self) -> None:
        day = date(2026, 10, 14)
        occurrences = [
            make_occurrence(day=day, hour=9, plan_id=1),
            make_occurrence(day=day, hour=11, plan_id=2),
        ]
        lanes = assign_lanes(occurrences)
        self.assertEqual(len(lanes), 2)
        self.assertTrue(all(count == 1 for _, count in lanes.values()))

    def test_overlapping_items_split_into_lanes(self) -> None:
        day = date(2026, 10, 14)
        a = make_occurrence(day=day, hour=9, plan_id=1, duration=60)
        b = make_occurrence(day=day, hour=9, plan_id=2, duration=60)
        lanes = assign_lanes([a, b])
        self.assertEqual(len(lanes), 2)
        self.assertEqual({count for _, count in lanes.values()}, {2})
        self.assertEqual(sorted(lane for lane, _ in lanes.values()), [0, 1])

    def test_chain_overlaps(self) -> None:
        day = date(2026, 10, 14)
        a = make_occurrence(day=day, hour=9, plan_id=1, duration=90)
        b = make_occurrence(day=day, hour=10, plan_id=2, duration=90)
        c = make_occurrence(day=day, hour=11, plan_id=3, duration=90)
        lanes = assign_lanes([a, b, c])
        # a 与 b 重叠，b 与 c 重叠 → 同一个簇里需要 2 条通道
        self.assertEqual({count for _, count in lanes.values()}, {2})
        self.assertEqual(len({lane for lane, _ in lanes.values()}), 2)


class WeekViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        qapp()

    def setUp(self) -> None:
        self.view = WeekView(LIGHT, datetime(2026, 10, 14, 10, 30))
        self.view.resize(1200, 720)
        self.view.show()
        qapp().processEvents()

    def tearDown(self) -> None:
        self.view.deleteLater()

    def test_seven_columns_with_monday_first(self) -> None:
        days = [column.day() for column in self.view.columns()]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0], date(2026, 10, 12))
        self.assertEqual(days[-1], date(2026, 10, 18))
        self.assertEqual(self.view.week_start(), date(2026, 10, 12))
        self.assertEqual(self.view.week_end(), date(2026, 10, 18))

    def test_today_is_highlighted_once(self) -> None:
        columns = self.view.columns()
        self.assertTrue(columns[2]._is_today)  # 10-14 周三
        self.assertEqual(sum(1 for column in columns if column._is_today), 1)

    def test_switch_week_updates_columns(self) -> None:
        self.view.set_week(date(2026, 10, 21))
        days = [column.day() for column in self.view.columns()]
        self.assertEqual(days[0], date(2026, 10, 19))
        # 10-14 已不在显示范围
        self.assertEqual(sum(1 for column in self.view.columns() if column._is_today), 0)

    def test_week_crossing_year(self) -> None:
        self.view.set_week(date(2026, 1, 1))
        days = [column.day() for column in self.view.columns()]
        self.assertEqual(days[0], date(2025, 12, 29))
        self.assertEqual(days[-1], date(2026, 1, 4))

    def test_occurrences_are_distributed_to_columns(self) -> None:
        day = date(2026, 10, 14)
        occurrences = [
            make_occurrence(day=day, hour=9, plan_id=1, title="上午任务"),
            make_occurrence(day=day, hour=15, plan_id=2, title="下午任务"),
            make_occurrence(day=day + timedelta(days=2), hour=10, plan_id=3, title="周五任务"),
        ]
        self.view.set_occurrences(occurrences)
        columns = self.view.columns()
        self.assertEqual(len(columns[2].occurrences()), 2)
        self.assertEqual(len(columns[4].occurrences()), 1)
        self.assertEqual(len(columns[0].occurrences()), 0)

        # 真的创建了绘制的任务块，并且同一时间互不重叠
        chips = columns[2].findChildren(EventChip)
        self.assertEqual(len(chips), 2)
        geometries = [chip.geometry() for chip in chips]
        self.assertEqual(len({(g.x(), g.y()) for g in geometries}), 2)

    def test_overlapping_chips_do_not_cover_each_other(self) -> None:
        day = date(2026, 10, 13)
        occurrences = [
            make_occurrence(day=day, hour=10, plan_id=1, duration=60),
            make_occurrence(day=day, hour=10, plan_id=2, duration=60),
        ]
        self.view.set_occurrences(occurrences)
        qapp().processEvents()
        column = self.view.columns()[1]
        chips = column.findChildren(EventChip)
        self.assertEqual(len(chips), 2)
        first, second = chips[0].geometry(), chips[1].geometry()
        self.assertNotEqual(first.x(), second.x())
        self.assertFalse(first.intersects(second))
        # 两个块都在同一列宽度之内
        self.assertLessEqual(max(first.right(), second.right()), column.width())

    def test_now_indicator_follows_current_time(self) -> None:
        before = self.view.now()
        self.view.set_now(datetime(2026, 10, 15, 8, 0))
        self.assertEqual(self.view.now().date(), date(2026, 10, 15))
        self.assertNotEqual(before, self.view.now())
        # 10-15 变成今天，之前的高亮消失
        self.assertTrue(self.view.columns()[3]._is_today)
        self.assertFalse(self.view.columns()[2]._is_today)

    def test_scroll_positions_do_not_crash(self) -> None:
        self.view.show()
        self.view.scroll_to_now()
        self.view.scroll_to_hour(8)
        self.view.scroll_to_default()

    # -- 跨天 / 真实起止时间 ------------------------------------------
    def test_same_day_end_time_sizes_block_like_course_block(self) -> None:
        occ = make_occurrence(
            day=date(2026, 10, 14),
            hour=9,
            duration=120,
            end_at=datetime(2026, 10, 14, 11, 0),
        )
        self.view.set_occurrences([occ])
        qapp().processEvents()
        chip = self.view.columns()[2].findChildren(EventChip)[0]
        self.assertFalse(chip.is_continuation)
        self.assertEqual(chip.y(), COLUMN_PAD_Y + int(9 * 60 / 60 * HOUR_HEIGHT))
        self.assertEqual(chip.height(), int(120 / 60 * HOUR_HEIGHT) - 2)
        self.assertEqual(chip._time_text(), "09:00-11:00")

    def test_legacy_plan_keeps_the_short_block(self) -> None:
        occ = make_occurrence(day=date(2026, 10, 14), hour=9, duration=45)
        self.view.set_occurrences([occ])
        qapp().processEvents()
        chip = self.view.columns()[2].findChildren(EventChip)[0]
        self.assertEqual(chip.height(), int(45 / 60 * HOUR_HEIGHT) - 2)

    def test_cross_day_plan_is_drawn_on_every_covered_day(self) -> None:
        occ = make_cross_day_occurrence(
            start_day=date(2026, 10, 13), end_day=date(2026, 10, 15)
        )
        self.view.set_occurrences([occ])
        qapp().processEvents()
        columns = self.view.columns()
        self.assertEqual([len(column.occurrences()) for column in columns[:4]], [0, 1, 1, 1])
        self.assertEqual([len(column.occurrences()) for column in columns[4:]], [0, 0, 0])

        start_chip = columns[1].findChildren(EventChip)[0]
        middle_chip = columns[2].findChildren(EventChip)[0]
        end_chip = columns[3].findChildren(EventChip)[0]

        # 开始那天：开始时间 → 23:00
        self.assertFalse(start_chip.is_continuation)
        self.assertEqual(start_chip.y(), COLUMN_PAD_Y + int(22 * 60 / 60 * HOUR_HEIGHT))
        self.assertEqual(start_chip.height(), int((23 * 60 - 22 * 60) / 60 * HOUR_HEIGHT) - 2)

        # 中间那天：约 12:00 位置的细横条
        self.assertTrue(middle_chip.is_continuation)
        self.assertEqual(middle_chip.height(), CONTINUATION_HEIGHT)
        self.assertEqual(
            middle_chip.y(),
            COLUMN_PAD_Y + int(CONTINUATION_AT_MINUTES / 60 * HOUR_HEIGHT),
        )
        self.assertIn("跨天任务", middle_chip._tooltip())

        # 结束那天：07:00 → 结束时间
        self.assertFalse(end_chip.is_continuation)
        self.assertEqual(end_chip.y(), COLUMN_PAD_Y + int(7 * 60 / 60 * HOUR_HEIGHT))
        self.assertEqual(end_chip.height(), int((9 * 60 + 30 - 7 * 60) / 60 * HOUR_HEIGHT) - 2)

    def test_cross_day_only_draws_current_week_part(self) -> None:
        # 10-11（上周日）22:00 → 10-13 09:30，本周只应画出 10-12 的延续和 10-13 的结束
        occ = make_cross_day_occurrence(
            start_day=date(2026, 10, 11), end_day=date(2026, 10, 13)
        )
        self.view.set_occurrences([occ])
        qapp().processEvents()
        columns = self.view.columns()
        self.assertEqual([len(column.occurrences()) for column in columns[:2]], [1, 1])
        self.assertEqual([len(column.occurrences()) for column in columns[2:]], [0, 0, 0, 0, 0])
        self.assertTrue(columns[0].findChildren(EventChip)[0].is_continuation)
        self.assertFalse(columns[1].findChildren(EventChip)[0].is_continuation)

    def test_continuation_bar_is_clickable(self) -> None:
        occ = make_cross_day_occurrence(
            start_day=date(2026, 10, 13), end_day=date(2026, 10, 15)
        )
        clicked: list[int] = []
        self.view.task_clicked.connect(clicked.append)
        self.view.set_occurrences([occ])
        qapp().processEvents()
        chip = self.view.columns()[2].findChildren(EventChip)[0]
        self.assertTrue(chip.is_continuation)
        chip.clicked.emit(chip.occurrence.task_id)
        self.assertEqual(clicked, [occ.task_id])

    def test_task_block_alpha_is_semi_transparent(self) -> None:
        # 约 0.78 不透明度，课程块会从下面透出来
        from src.weekly_calendar import TASK_FILL_ALPHA

        self.assertTrue(0.75 <= TASK_FILL_ALPHA / 255 <= 0.82)


class MainWindowTest(unittest.TestCase):
    """主窗口集成：真实数据、周导航、搜索、主题切换。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = qapp()

    def setUp(self) -> None:
        from src.main_window import MainWindow

        self.env = TestEnv("window")
        self.theme = ThemeManager(self.app)
        self.theme.apply("light")
        self.window = MainWindow(self.env.service, self.theme)
        self.window.resize(1280, 800)

    def tearDown(self) -> None:
        try:
            self.window.force_close()
        finally:
            self.window.deleteLater()
            self.env.close()

    def test_opens_on_current_week(self) -> None:
        today = datetime.now().date()
        self.assertEqual(self.window.week_view.week_start(), start_of_week(today))
        self.assertEqual(len(self.window.week_view.columns()), 7)
        self.assertEqual(self.window.month_label.text(), f"{today.year} 年 {today.month} 月")

    def test_navigation_buttons(self) -> None:
        start = self.window.week_view.week_start()
        self.window._shift_week(1)
        self.assertEqual(self.window.week_view.week_start(), start + timedelta(days=7))
        self.assertTrue(self.window.today_button.isEnabled())
        self.window._shift_week(-1)
        self.assertEqual(self.window.week_view.week_start(), start)
        self.window._shift_week(2)
        self.window.go_today()
        self.assertEqual(self.window.week_view.week_start(), start)
        self.assertFalse(self.window.today_button.isEnabled())

    def test_task_appears_in_week_view(self) -> None:
        # 放在今天（今天一定在当前显示的周里），不依赖当前具体时刻
        plan_time = datetime.combine(datetime.now().date(), datetime.min.time()).replace(hour=15, minute=0)
        task_id = self.env.create_task(
            title="界面里的任务",
            due_at=plan_time + timedelta(days=1),
            plans=[PlanDraft(plan_at=plan_time, label="计划")],
        )
        self.window.refresh()
        chips = self.window.week_view.findChildren(EventChip)
        self.assertGreaterEqual(len(chips), 1)
        self.assertIn(task_id, [chip.occurrence.task_id for chip in chips])

    def test_search_filters_week_view(self) -> None:
        today = datetime.now().date()
        plan_time = datetime.combine(today, datetime.min.time()).replace(hour=13, minute=0)
        self.env.create_task(
            title="独一无二的任务名",
            due_at=plan_time + timedelta(days=1),
            plans=[PlanDraft(plan_at=plan_time)],
        )
        self.window.refresh()
        self.assertGreaterEqual(len(self.window.week_view.findChildren(EventChip)), 1)

        self.window.search_edit.setText("完全不匹配")
        self.window._on_search_changed()
        self.assertEqual(len(self.window.week_view.findChildren(EventChip)), 0)

        self.window.search_edit.setText("独一无二")
        self.window._on_search_changed()
        self.assertGreaterEqual(len(self.window.week_view.findChildren(EventChip)), 1)

    def test_theme_switch(self) -> None:
        self.theme.apply("dark")
        self.window.apply_theme()
        self.assertEqual(self.window.theme_manager.resolved, "dark")
        self.theme.apply("light")
        self.window.apply_theme()
        self.assertEqual(self.window.theme_manager.resolved, "light")

    def test_completed_task_is_marked(self) -> None:
        today = datetime.now().date()
        plan_time = datetime.combine(today, datetime.min.time()).replace(hour=16, minute=0)
        task_id = self.env.create_task(title="已完成任务", due_at=plan_time, plans=[PlanDraft(plan_at=plan_time)])
        self.window.refresh()
        self.env.service.set_status(task_id, "done")
        self.window.refresh()
        chips = [chip for chip in self.window.week_view.findChildren(EventChip) if chip.occurrence.task_id == task_id]
        self.assertTrue(chips)
        self.assertTrue(all(chip.occurrence.is_done for chip in chips))

    def test_cross_day_task_is_drawn_across_days(self) -> None:
        # 用本周二 22:00 → 周三 10:00，保证完全落在当前显示的周里
        week_start = self.window.week_view.week_start()
        start = datetime.combine(week_start + timedelta(days=1), time(22, 0))
        end = start + timedelta(hours=12)
        task_id = self.env.create_task(
            title="跨天界面任务",
            due_at=start + timedelta(days=3),
            plans=[
                PlanDraft(plan_at=start, end_at=end, remind_start=True, remind_end=True)
            ],
        )
        self.window.refresh()
        chips = [
            chip
            for chip in self.window.week_view.findChildren(EventChip)
            if chip.occurrence.task_id == task_id
        ]
        # 开始日一块 + 结束日一块（至少 2 块）
        self.assertGreaterEqual(len(chips), 2)
        self.assertTrue(any(not chip.is_continuation for chip in chips))
        self.window.week_view.grab()  # 强制绘制，确保跨天块不会抛异常


if __name__ == "__main__":
    unittest.main()
