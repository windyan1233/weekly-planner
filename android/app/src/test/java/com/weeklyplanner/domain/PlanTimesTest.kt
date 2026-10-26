package com.weeklyplanner.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

/** 计划时间的纯计算：周视图分段、列表文案、保存校验。 */
class PlanTimesTest {
    private val zone = ZoneId.systemDefault()

    /** 2026-09-21 是周一。 */
    private val weekStart = LocalDate.of(2026, 9, 21)

    private fun at(date: LocalDate, hour: Int, minute: Int): Long =
        date.atTime(LocalTime.of(hour, minute)).atZone(zone).toInstant().toEpochMilli()

    private fun segments(planAt: Long, endAt: Long?): List<PlanSegment> =
        PlanTimes.segments(planAt = planAt, endAt = endAt, weekStart = weekStart, zone = zone)

    @Test
    fun legacy_plan_without_end_keeps_45_minute_block() {
        val start = at(LocalDate.of(2026, 9, 23), 10, 0)
        val result = segments(start, null)
        assertEquals(1, result.size)
        assertEquals(LocalDate.of(2026, 9, 23), result[0].date)
        assertEquals(600, result[0].startMinutes)
        assertEquals(645, result[0].endMinutes)
        assertFalse(result[0].continuation)
    }

    @Test
    fun same_day_plan_uses_real_start_and_end() {
        val start = at(LocalDate.of(2026, 9, 22), 9, 0)
        val end = at(LocalDate.of(2026, 9, 22), 11, 30)
        val result = segments(start, end)
        assertEquals(1, result.size)
        assertEquals(LocalDate.of(2026, 9, 22), result[0].date)
        assertEquals(540, result[0].startMinutes)
        assertEquals(690, result[0].endMinutes)
        assertFalse(result[0].continuation)
    }

    @Test
    fun cross_day_start_day_runs_to_2300_and_end_day_from_0700() {
        val start = at(LocalDate.of(2026, 9, 22), 22, 0)
        val end = at(LocalDate.of(2026, 9, 24), 9, 30)
        val result = segments(start, end)
        assertEquals(3, result.size)

        // 开始那天：22:00 -> 23:00
        assertEquals(LocalDate.of(2026, 9, 22), result[0].date)
        assertEquals(22 * 60, result[0].startMinutes)
        assertEquals(23 * 60, result[0].endMinutes)
        assertFalse(result[0].continuation)

        // 中间那天：只画 12:00 的延续条
        assertEquals(LocalDate.of(2026, 9, 23), result[1].date)
        assertTrue(result[1].continuation)
        assertEquals(PlanTimes.CONTINUATION_MINUTES, result[1].startMinutes)
        assertEquals(PlanTimes.CONTINUATION_MINUTES, result[1].endMinutes)

        // 结束那天：07:00 -> 09:30
        assertEquals(LocalDate.of(2026, 9, 24), result[2].date)
        assertEquals(7 * 60, result[2].startMinutes)
        assertEquals(9 * 60 + 30, result[2].endMinutes)
        assertFalse(result[2].continuation)
    }

    @Test
    fun only_the_week_part_of_a_long_plan_is_drawn() {
        val start = at(LocalDate.of(2026, 9, 20), 22, 0) // 上周日
        val end = at(LocalDate.of(2026, 10, 1), 10, 0)
        val result = segments(start, end)
        assertEquals(7, result.size)
        assertTrue(result.all { it.continuation })
        assertEquals(LocalDate.of(2026, 9, 21), result.first().date)
        assertEquals(LocalDate.of(2026, 9, 27), result.last().date)
    }

    @Test
    fun plan_ending_after_the_week_is_cut_at_sunday() {
        val start = at(LocalDate.of(2026, 9, 25), 20, 0) // 周五
        val end = at(LocalDate.of(2026, 9, 29), 9, 0) // 下周二
        val result = segments(start, end)
        assertEquals(
            listOf(
                LocalDate.of(2026, 9, 25),
                LocalDate.of(2026, 9, 26),
                LocalDate.of(2026, 9, 27)
            ),
            result.map { it.date }
        )
        assertEquals(20 * 60, result[0].startMinutes)
        assertEquals(23 * 60, result[0].endMinutes)
        assertTrue(result[1].continuation)
        assertTrue(result[2].continuation)
    }

    @Test
    fun plan_outside_the_week_is_ignored() {
        val otherDay = LocalDate.of(2026, 10, 5)
        assertTrue(segments(at(otherDay, 9, 0), at(otherDay, 10, 0)).isEmpty())
        assertTrue(segments(at(otherDay, 9, 0), null).isEmpty())
    }

    @Test
    fun labels_for_all_three_shapes() {
        val sameDayStart = at(LocalDate.of(2026, 9, 22), 9, 0)
        val sameDayEnd = at(LocalDate.of(2026, 9, 22), 11, 30)
        assertEquals("09:00", PlanTimes.listLabel(sameDayStart, null))
        assertEquals("09:00-11:30", PlanTimes.listLabel(sameDayStart, sameDayEnd))

        val crossStart = at(LocalDate.of(2026, 9, 22), 22, 0)
        val crossEnd = at(LocalDate.of(2026, 9, 24), 9, 30)
        assertEquals("09-22 22:00 → 09-24 09:30 · 跨3天", PlanTimes.listLabel(crossStart, crossEnd))
        assertEquals(3, PlanTimes.daySpan(crossStart, crossEnd))
        assertTrue(PlanTimes.isCrossDay(crossStart, crossEnd))
        assertFalse(PlanTimes.isCrossDay(sameDayStart, sameDayEnd))

        // 非法区间（结束早于开始）按「没有结束时间」处理，保持原来的显示
        assertEquals("09:00", PlanTimes.listLabel(sameDayStart, sameDayStart - 60_000L))
    }

    @Test
    fun validate_checks_end_after_start_and_duplicate_starts() {
        val start = at(LocalDate.of(2026, 9, 22), 9, 0)
        assertNull(PlanTimes.validate(emptyList()))
        assertNull(PlanTimes.validate(listOf(PlanDraft(startAt = start))))
        assertNull(PlanTimes.validate(listOf(PlanDraft(startAt = start, endAt = start + 3_600_000))))

        val backwards = PlanTimes.validate(
            listOf(
                PlanDraft(startAt = start),
                PlanDraft(startAt = start + 7_200_000, endAt = start + 7_200_000)
            )
        )
        val backwardsMessage = requireNotNull(backwards)
        assertTrue(backwardsMessage.contains("第 2 个计划"))
        assertTrue(backwardsMessage.contains("结束时间要晚于开始时间"))

        val duplicated = requireNotNull(
            PlanTimes.validate(listOf(PlanDraft(startAt = start), PlanDraft(startAt = start)))
        )
        assertTrue(duplicated.contains("开始时间相同"))
    }
}
