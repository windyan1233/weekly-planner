package com.weeklyplanner.courses

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TimetableReaderTest {
    @Test
    fun flat_detail_rows_are_parsed() {
        val rows = listOf(
            listOf("序号", "星期", "节次", "课程名称", "周次", "校区", "场地", "教师"),
            listOf("1", "星期一", "3-4", "体能训练（1）●", "4-6周(双),7-16周", "南湖校区", "第一田径场", "韩林")
        )
        val parsed = FlatCsvParser.parse(rows)
        assertEquals(1, parsed.courses.size)
        assertTrue(!parsed.hasTimetableTimes)
        assertEquals("体能训练（1）", parsed.courses[0].name)
        assertEquals("第一田径场", parsed.courses[0].location)
        assertEquals(listOf(3, 4), parsed.courses[0].periods)
    }

    @Test
    fun long_lab_course_uses_all_periods() {
        val header = listOf("", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
        val cell = """
            无机化学实验
            (2026级药学（理科基地班）一班（93K）)
            何丽丽,临时助教
            7-8,10,12([周])
            [01-02-03-04-05-06-07-08节]
            第二实验楼无机化学实验室
        """.trimIndent()
        val rows = listOf(
            listOf("标题"),
            listOf("学年学期"),
            header,
            listOf("第1~2节\n08:00-09:30", cell, "", "", "", "", "", ""),
            listOf("第3~5节\n09:50-12:00", "", "", "", "", "", "", ""),
            listOf("第6~7节\n14:00-15:25", "", "", "", "", "", "", ""),
            listOf("第8~9节\n15:45-17:10", "", "", "", "", "", "", "")
        )
        val parsed = TimetableParser.parse(rows)
        assertEquals(1, parsed.courses.size)
        assertEquals((1..8).toList(), parsed.courses[0].periods)
        assertEquals(8 * 60, parsed.courses[0].startMinutes)
        assertEquals(17 * 60 + 10, parsed.courses[0].endMinutes)
    }

    @Test
    fun split_week_and_period_lines_are_parsed() {
        val header = listOf("", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
        val rows = listOf(
            listOf("标题"),
            listOf("学年学期：2026-2027-1"),
            header,
            listOf(
                "第1~2节\n08:00-09:30",
                "\n逻辑学\n张玉志\n1-16[周]\nJS203\n[01-02]节",
                "", "", "", "", "", ""
            )
        )
        val parsed = TimetableParser.parse(rows)
        assertEquals(1, parsed.courses.size)
        assertEquals("逻辑学", parsed.courses[0].name)
        assertEquals(listOf(1, 2), parsed.courses[0].periods)
        assertEquals(8 * 60, parsed.courses[0].startMinutes)
        assertEquals(9 * 60 + 30, parsed.courses[0].endMinutes)
        assertTrue(parsed.hasTimetableTimes)
    }
}
