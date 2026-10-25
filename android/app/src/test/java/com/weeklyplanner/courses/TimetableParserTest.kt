package com.weeklyplanner.courses

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class TimetableParserTest {
    private fun sampleRows(): List<List<String>> = listOf(
        listOf("某某大学 张三 学生个人课表"),
        listOf("学年学期：2026-2027-1"),
        listOf("", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
        listOf(
            "第一大节\n(01,02)\n08:30-10:05",
            "\n军事技能训练\n\n1-2([周])[01-02-03-04-05-06-07-08节]\n校本部操场\n\n高等数学I\n张三\n3-4,7-17([周])[01-02节]\n图一\n",
            "高等数学I\n张三\n3-4,7-17([周])[01-02节]\n图一\n",
            "", "", "", "", ""
        ),
        listOf(
            "第二大节\n(03,04)\n10:25-12:00",
            "\n美术鉴赏\n李四\n11-14([周])[03-04节]\n图二\n",
            "", "", "", "", "", ""
        )
    )

    @Test
    fun parses_grid_timetable() {
        val result = TimetableParser.parse(sampleRows())
        assertTrue(result.courses.isNotEmpty())
        val math = result.courses.first { it.name == "高等数学I" && it.weekday == 0 }
        assertEquals(listOf(3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17), math.weeks)
        assertEquals(listOf(1, 2), math.periods)
        assertEquals(8 * 60 + 30, math.startMinutes)
        assertEquals(10 * 60 + 5, math.endMinutes)
        assertEquals("张三", math.teacher)
        assertEquals("图一", math.location)
        assertEquals(0, math.weekday)

        val military = result.courses.first { it.name == "军事技能训练" }
        assertEquals(listOf(1, 2), military.weeks)
        assertEquals(8, military.periods.size)

        val art = result.courses.first { it.name == "美术鉴赏" }
        assertEquals(10 * 60 + 25, art.startMinutes)
    }

    @Test
    fun grid_without_times_uses_default_section_times() {
        val rows = listOf(
            listOf("", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
            listOf(
                "第一大节\n(01,02)",
                "高等数学I\n张三\n3-4([周])[1-2节]\n图一",
                "", "", "", "", "", ""
            )
        )
        val result = TimetableParser.parse(rows)
        assertTrue(!result.hasTimetableTimes)
        assertEquals(8 * 60 + 30, result.courses.first().startMinutes)
        assertEquals(10 * 60 + 5, result.courses.first().endMinutes)
    }

    @Test
    fun apply_custom_times_recomputes_start_and_end() {
        val course = ParsedCourse(
            name = "高等数学I",
            teacher = "张三",
            location = "图一",
            descriptor = "",
            weekday = 0,
            weeks = listOf(1),
            periods = listOf(1, 2),
            startMinutes = 0,
            endMinutes = 0
        )
        val adjusted = TimetableParser.applyTimes(
            listOf(course),
            mapOf(1 to (8 * 60 to 9 * 60 + 30), 2 to (8 * 60 to 9 * 60 + 30))
        )
        assertEquals(8 * 60, adjusted.first().startMinutes)
        assertEquals(9 * 60 + 30, adjusted.first().endMinutes)
    }

    @Test
    fun parses_weeks_expression() {
        assertEquals(listOf(3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17), TimetableParser.parseWeeks("3-4,7-17([周])"))
        assertEquals(listOf(6), TimetableParser.parseWeeks("6([周])"))
        assertEquals(listOf(1, 3, 5), TimetableParser.parseWeeks("1-6单周"))
        assertEquals(listOf(2, 4, 6), TimetableParser.parseWeeks("2-6双周"))
    }

    @Test
    fun expands_to_real_dates() {
        val result = TimetableParser.parse(sampleRows())
        val sessions = TimetableParser.expandSessions(result.courses, LocalDate.of(2026, 9, 7))
        val mathWeek3 = sessions.first {
            it.course.name == "高等数学I" && it.day == LocalDate.of(2026, 9, 21) && it.course.weekday == 0
        }
        assertEquals(8 * 60 + 30, mathWeek3.startMinutes)
    }

    @Test
    fun flat_csv_is_detected_and_parsed() {
        val rows = listOf(
            listOf("课程", "星期", "节次", "周次", "时间", "地点", "教师"),
            listOf("高等数学I", "星期一", "01-02", "3-4,7-17", "08:30-10:05", "图一", "张三"),
            listOf("体育I", "周三", "07-08", "3-4,7-17", "", "操场", "李四")
        )
        assertTrue(!FlatCsvParser.isGrid(rows))
        val result = FlatCsvParser.parse(rows)
        assertEquals(2, result.courses.size)
        val sports = result.courses.first { it.name == "体育I" }
        assertEquals(2, sports.weekday)
        assertEquals(15 * 60 + 25, sports.startMinutes)
        assertEquals(17 * 60, sports.endMinutes)
        assertEquals(26, result.sessionCount)
    }

    @Test(expected = ParseError::class)
    fun rejects_non_timetable() {
        TimetableParser.parse(listOf(listOf("随便什么"), listOf("没有表头")))
    }
}
