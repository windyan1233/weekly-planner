"""课表导入测试：xls 读取、解析、入库与周视图课程块。"""

from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path

from tests.support import ROOT, qapp

import unittest

from src.courses.course_store import CourseStore
from src.courses.import_dialog import (
    looks_like_grid,
    parse_rows,
    read_csv_rows,
    read_table_rows,
)
from src.courses.timetable_parser import (
    ParseError,
    expand_sessions,
    format_weeks,
    ParsedCourse,
    apply_times,
    parse_flat_rows,
    parse_timetable,
    parse_weeks,
)
from src.courses.xls_reader import XlsError, read_xls_rows
from src.database import Database

FIXTURE = ROOT / "tests" / "fixtures" / "student_schedule.xls"
RESAVED = ROOT / "tests" / "fixtures" / "student_schedule_resaved.xls"


def sample_rows() -> list[list[str]]:
    """仿照教务系统导出的课表结构（含老师为空、跨大节的课程）。"""
    return [
        ["某某大学 张三 学生个人课表"],
        ["学年学期：2026-2027-1        班级：测试班"],
        ["", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
        [
            "第一大节\n(01,02)\n08:30-10:05",
            "\n军事技能训练\n\n1-2([周])[01-02-03-04-05-06-07-08节]\n校本部操场\n\n"
            "高等数学I\n张三\n3-4,7-17([周])[01-02节]\n图一\n\n"
            "科研能力训练I\n\n18([周])[01-02-03-04-05-06-07-08节]\n",
            "\n高等数学I\n张三\n3-4,7-17([周])[01-02节]\n图一\n\n"
            "科研能力训练I\n\n18([周])[01-02-03-04-05-06-07-08节]\n",
            "",
            "",
            "",
            "",
            "",
        ],
        [
            "第二大节\n(03,04)\n10:25-12:00",
            "\n美术鉴赏\n李四\n11-14([周])[03-04节]\n图二\n",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
    ]


class ParserTest(unittest.TestCase):
    def test_parse_sample(self) -> None:
        result = parse_timetable(sample_rows())
        self.assertEqual(len(result.big_sections), 2)
        self.assertEqual(result.big_sections[0].start_minutes, 8 * 60 + 30)
        names = {(course.name, course.weekday) for course in result.courses}
        self.assertIn(("军事技能训练", 0), names)
        self.assertIn(("高等数学I", 0), names)
        self.assertIn(("高等数学I", 1), names)
        self.assertIn(("科研能力训练I", 0), names)
        self.assertIn(("美术鉴赏", 0), names)
        # 同一门课在多个大节里重复出现时只保留一条
        military = [c for c in result.courses if c.name == "军事技能训练"]
        self.assertEqual(len(military), 1)
        self.assertEqual(military[0].weeks, (1, 2))
        self.assertEqual(military[0].periods, (1, 2, 3, 4, 5, 6, 7, 8))
        self.assertEqual(military[0].start_minutes, 8 * 60 + 30)
        # 样例只给了前两个大节，5-8 节没有作息时间，按已映射的最大结束时间算
        self.assertEqual(military[0].end_minutes, 12 * 60)

    def test_grid_without_times_uses_defaults(self) -> None:
        rows = [
            ["", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
            [
                "第一大节\n(01,02)",
                "高等数学I\n张三\n3-4([周])[01-02节]\n图一",
                "", "", "", "", "", "",
            ],
        ]
        parsed = parse_timetable(rows)
        self.assertFalse(parsed.has_timetable_times)
        self.assertEqual(parsed.courses[0].start_minutes, 8 * 60 + 30)
        self.assertEqual(parsed.courses[0].end_minutes, 10 * 60 + 5)

    def test_apply_custom_times(self) -> None:
        course = ParsedCourse(
            name="高等数学I",
            weekday=0,
            weeks=(1,),
            periods=(1, 2),
            start_minutes=0,
            end_minutes=0,
        )
        adjusted = apply_times([course], {1: (8 * 60, 9 * 60 + 30), 2: (8 * 60, 9 * 60 + 30)})
        self.assertEqual(adjusted[0].start_minutes, 8 * 60)
        self.assertEqual(adjusted[0].end_minutes, 9 * 60 + 30)

    def test_xlsx_prefers_flat_detail_sheet(self) -> None:
        from openpyxl import Workbook

        workbook = Workbook()
        grid = workbook.active
        grid.title = "课表"
        grid.append(["", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"])
        grid.append(
            [
                "第一大节\n(01,02)\n08:30-10:05",
                "高等数学I\n张三\n1-2([周])[01-02节]\n图一",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        detail = workbook.create_sheet("课程明细")
        detail.append(["某某课表"])
        detail.append(["序号", "星期", "节次", "课程名称", "周次", "校区", "场地", "教师"])
        detail.append([1, "星期一", "3-4", "体能训练（1）●", "4-6周(双),7-16周", "南湖校区", "第一田径场", "韩林"])

        folder = ROOT / ".testdata" / "cases" / f"xlsx_{uuid.uuid4().hex[:8]}"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            path = folder / "timetable.xlsx"
            workbook.save(path)
            rows = read_table_rows(path)
            self.assertIn("课程名称", rows[1])
            self.assertFalse(looks_like_grid(rows))
            parsed = parse_rows(rows)
            self.assertFalse(parsed.has_timetable_times)
            self.assertEqual(len(parsed.courses), 1)
            course = parsed.courses[0]
            self.assertEqual(course.name, "体能训练（1）")
            self.assertEqual(course.location, "第一田径场")
            self.assertEqual(course.periods, (3, 4))
            self.assertEqual(
                course.weeks,
                (4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16),
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_weeks_expression(self) -> None:
        self.assertEqual(parse_weeks("3-4,7-17"), tuple(range(3, 5)) + tuple(range(7, 18)))
        self.assertEqual(parse_weeks("6"), (6,))
        self.assertEqual(parse_weeks("1-6单周"), (1, 3, 5))
        self.assertEqual(parse_weeks("2-6双周"), (2, 4, 6))
        self.assertEqual(format_weeks((1, 2, 3, 5, 6)), "1-3,5-6")

    def test_rejects_non_timetable(self) -> None:
        with self.assertRaises(ParseError):
            parse_timetable([["随便什么"], ["没有表头"]])

    def test_expand_sessions(self) -> None:
        result = parse_timetable(sample_rows())
        sessions = expand_sessions(result.courses, date(2026, 9, 7))
        military = [item for item in sessions if item[0].name == "军事技能训练"]
        self.assertEqual(len(military), 2)
        self.assertEqual(military[0][1], date(2026, 9, 7))

    @unittest.skipUnless(FIXTURE.exists(), "缺少真实课表样例文件")
    def test_real_export_parse(self) -> None:
        rows = read_xls_rows(FIXTURE)
        result = parse_timetable(rows)
        self.assertEqual(len(result.courses), 46)
        self.assertEqual(result.session_count, 215)
        names = {course.name for course in result.courses}
        self.assertIn("军事技能训练", names)
        self.assertIn("人工智能通识课", names)
        self.assertIn("无机化学实验", names)

    @unittest.skipUnless(RESAVED.exists(), "缺少重新保存过的课表样例")
    def test_resaved_xls(self) -> None:
        # 用 Excel/WPS 重新保存后，字符串会跨 CONTINUE 记录，SST 要能正确解码
        rows = read_xls_rows(RESAVED)
        parsed = parse_timetable(rows)
        self.assertEqual(len(parsed.courses), 46)
        self.assertEqual(parsed.session_count, 215)
        self.assertEqual(parsed.big_sections[0].start_minutes, 8 * 60)
        self.assertEqual(parsed.big_sections[0].end_minutes, 9 * 60 + 50)
        self.assertEqual(parsed.big_sections[2].end_minutes, 15 * 60 + 20)

    def test_xls_reader_rejects_wrong_file(self) -> None:
        path = ROOT / ".testdata" / "cases" / f"notxls_{uuid.uuid4().hex[:6]}.xls"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not an excel file")
        try:
            with self.assertRaises(XlsError):
                read_xls_rows(path)
        finally:
            path.unlink(missing_ok=True)


class CsvImportTest(unittest.TestCase):
    def test_grid_csv(self) -> None:
        import csv
        import io

        rows = sample_rows()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerows(rows)
        data = buffer.getvalue().encode("utf-8-sig")
        parsed_rows = read_csv_rows(data)
        self.assertTrue(looks_like_grid(parsed_rows))
        parsed = parse_rows(parsed_rows)
        self.assertIn("高等数学I", {course.name for course in parsed.courses})

    def test_gbk_encoding(self) -> None:
        text = "课程,星期,节次,周次,地点,教师\n高等数学I,星期一,01-02,3-4,图一,胡忠盛\n"
        rows = read_csv_rows(text.encode("gb18030"))
        self.assertEqual(rows[1][0], "高等数学I")

    def test_flat_csv(self) -> None:
        text = (
            "课程,星期,节次,周次,时间,地点,教师\n"
            "高等数学I,星期一,01-02,3-4,7-17,08:30-10:05,图一,胡忠盛\n"
            "体育I,周三,07-08,3-4,7-17,,校本部操场,闫欣\n"
            "军事技能训练,星期二,01-02-03-04-05-06-07-08,1-2,,校本部操场,\n"
        )
        parsed = parse_flat_rows(read_csv_rows(text.encode("utf-8")))
        names = {(course.name, course.weekday) for course in parsed.courses}
        self.assertIn(("高等数学I", 0), names)
        self.assertIn(("体育I", 2), names)
        self.assertIn(("军事技能训练", 1), names)
        sports = next(course for course in parsed.courses if course.name == "体育I")
        # 没写时间时按默认大节时间映射
        self.assertEqual((sports.start_minutes, sports.end_minutes), (15 * 60 + 25, 17 * 60))
        math = next(course for course in parsed.courses if course.name == "高等数学I")
        self.assertEqual((math.start_minutes, math.end_minutes), (8 * 60 + 30, 10 * 60 + 5))

    def test_flat_csv_missing_weeks(self) -> None:
        text = "课程,星期,节次,周次\n没有周次,星期一,01-02,\n"
        with self.assertRaises(ParseError):
            parse_flat_rows(read_csv_rows(text.encode("utf-8")))


class CourseStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        base = ROOT / ".testdata" / "cases"
        base.mkdir(parents=True, exist_ok=True)
        self.dir = base / f"courses_{uuid.uuid4().hex[:8]}"
        self.dir.mkdir()
        self.db = Database(self.dir / "planner.db")
        self.store = CourseStore(self.db)

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_import_and_query(self) -> None:
        result = parse_timetable(sample_rows())
        courses, sessions = self.store.replace(result, date(2026, 9, 7))
        self.assertGreaterEqual(courses, 4)
        self.assertEqual(sessions, sum(len(c.weeks) for c in result.courses))
        # 第 3 周周一 = 2026-09-21，高等数学I 08:30-10:05
        blocks = self.store.blocks_between(date(2026, 9, 21), date(2026, 9, 27))
        high_math = [b for b in blocks if b.name == "高等数学I"]
        self.assertTrue(high_math)
        first = high_math[0]
        self.assertEqual(first.day, date(2026, 9, 21))
        self.assertEqual((first.start_minutes, first.end_minutes), (510, 605))
        # 第 2 周没有高等数学（3-4,7-17）
        week2 = self.store.blocks_between(date(2026, 9, 14), date(2026, 9, 20))
        self.assertFalse([b for b in week2 if b.name == "高等数学I"])

    def test_replace_and_clear(self) -> None:
        result = parse_timetable(sample_rows())
        self.store.replace(result, date(2026, 9, 7))
        self.store.replace(result, date(2026, 9, 7))
        courses, sessions = self.store.stats()
        self.assertLessEqual(courses, 5)
        self.store.clear()
        self.assertEqual(self.store.stats(), (0, 0))
        self.assertEqual(self.store.blocks_between(date(2026, 1, 1), date(2026, 12, 31)), [])

    def test_week_view_receives_courses(self) -> None:
        from src.weekly_calendar import WeekView

        app = qapp()
        result = parse_timetable(sample_rows())
        self.store.replace(result, date(2026, 9, 7))
        view = WeekView()
        from datetime import datetime

        view.set_week(date(2026, 9, 21))
        blocks = self.store.blocks_between(view.week_start(), view.week_end())
        view.set_course_blocks(blocks)
        app.processEvents()
        monday = view.columns()[0]
        self.assertTrue(monday._course_blocks)
        self.assertEqual(monday._course_blocks[0].start_minutes, 510)
        view.deleteLater()
