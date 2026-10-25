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
}
