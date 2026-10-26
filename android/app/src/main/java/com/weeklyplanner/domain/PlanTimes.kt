package com.weeklyplanner.domain

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

/**
 * 编辑界面用的计划时间草稿：一个任务可以有多条。
 *
 * 和 [com.weeklyplanner.data.PlanTimeEntity] 一一对应，但不带 taskId，
 * 保存时由 ViewModel 补上。新建的计划 [id] 为 0。
 */
data class PlanDraft(
    val id: Long = 0L,
    val startAt: Long,
    val endAt: Long? = null,
    val remindStart: Boolean = true,
    val remindEnd: Boolean = false
)

/** 周视图里计划时间落在某一天的片段（分钟数从当天 00:00 起算）。 */
data class PlanSegment(
    val date: LocalDate,
    val startMinutes: Int,
    val endMinutes: Int,
    /** 跨天计划在中间那些天只画一条细的延续条，不是真实区间。 */
    val continuation: Boolean = false
)

/**
 * 计划时间的纯计算部分：周视图分段、列表文案、保存前的校验。
 *
 * 这里不依赖 Compose / Room，方便直接用 JVM 单元测试覆盖。
 */
object PlanTimes {
    /** 旧数据没有结束时间时，按 45 分钟的块显示。 */
    const val LEGACY_MINUTES = 45

    /** 跨天计划在中间那天画延续条的位置：12:00。 */
    const val CONTINUATION_MINUTES = 12 * 60

    /** 时间轴默认可见范围：07:00 - 23:00。 */
    const val DEFAULT_DAY_START_MINUTES = 7 * 60
    const val DEFAULT_DAY_END_MINUTES = 23 * 60

    private val clockFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")
    private val listFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("MM-dd HH:mm")

    /** 有结束时间、并且结束时间真的晚于开始时间，才算区间计划。 */
    fun hasRange(planAt: Long, endAt: Long?): Boolean = endAt != null && endAt > planAt

    fun isCrossDay(planAt: Long, endAt: Long?, zone: ZoneId = ZoneId.systemDefault()): Boolean {
        if (!hasRange(planAt, endAt)) return false
        return localDate(planAt, zone) != localDate(endAt!!, zone)
    }

    /** 跨了几天（含首尾）；不跨天返回 1。 */
    fun daySpan(planAt: Long, endAt: Long?, zone: ZoneId = ZoneId.systemDefault()): Int {
        if (!hasRange(planAt, endAt)) return 1
        val start = localDate(planAt, zone)
        val end = localDate(endAt!!, zone)
        return (ChronoUnit.DAYS.between(start, end).toInt() + 1).coerceAtLeast(1)
    }

    /**
     * 把一条计划拆成「本周内、按天」的绘制片段。
     *
     * - 同一天：真实开始 -> 结束；
     * - 跨天的开始那天：开始 -> 当天 23:00；
     * - 跨天的结束那天：07:00 -> 结束；
     * - 跨天的中间每天：12:00 处的延续条（[PlanSegment.continuation]）；
     * - 没有结束时间：沿用 45 分钟块。
     *
     * 超出可见时间轴（默认 07:00-23:00）的部分会被裁掉，完全看不见的片段不返回。
     */
    fun segments(
        planAt: Long,
        endAt: Long?,
        weekStart: LocalDate,
        weekDays: Int = 7,
        dayStartMinutes: Int = DEFAULT_DAY_START_MINUTES,
        dayEndMinutes: Int = DEFAULT_DAY_END_MINUTES,
        zone: ZoneId = ZoneId.systemDefault()
    ): List<PlanSegment> {
        if (weekDays <= 0) return emptyList()
        val firstDay = weekStart
        val lastDay = weekStart.plusDays((weekDays - 1).toLong())
        val startDate = localDate(planAt, zone)
        val startMinute = minuteOfDay(planAt, zone)

        if (!hasRange(planAt, endAt)) {
            if (startDate < firstDay || startDate > lastDay) return emptyList()
            val legacy = PlanSegment(startDate, startMinute, startMinute + LEGACY_MINUTES)
            return listOfNotNull(clip(legacy, dayStartMinutes, dayEndMinutes))
        }

        val endDate = localDate(endAt!!, zone)
        val endMinute = minuteOfDay(endAt, zone)
        val result = mutableListOf<PlanSegment>()
        var date = maxOf(startDate, firstDay)
        val last = minOf(endDate, lastDay)
        while (!date.isAfter(last)) {
            val isContinuation = date != startDate && date != endDate
            if (isContinuation) {
                result += PlanSegment(
                    date = date,
                    startMinutes = CONTINUATION_MINUTES,
                    endMinutes = CONTINUATION_MINUTES,
                    continuation = true
                )
            } else {
                val segmentStart = if (date == startDate) startMinute else dayStartMinutes
                val segmentEnd = if (date == endDate) endMinute else dayEndMinutes
                clip(PlanSegment(date, segmentStart, segmentEnd), dayStartMinutes, dayEndMinutes)
                    ?.let { result += it }
            }
            date = date.plusDays(1)
        }
        return result
    }

    /**
     * 列表里的时间文案：
     * - 没有结束时间：`HH:mm`（和原来一致）；
     * - 同一天：`HH:mm-HH:mm`；
     * - 跨天：`MM-dd HH:mm → MM-dd HH:mm · 跨N天`。
     */
    fun listLabel(planAt: Long, endAt: Long?, zone: ZoneId = ZoneId.systemDefault()): String {
        if (!hasRange(planAt, endAt)) return clockText(planAt, zone)
        val start = Instant.ofEpochMilli(planAt).atZone(zone)
        val end = Instant.ofEpochMilli(endAt!!).atZone(zone)
        return if (start.toLocalDate() == end.toLocalDate()) {
            "${start.format(clockFormatter)}-${end.format(clockFormatter)}"
        } else {
            "${start.format(listFormatter)} → ${end.format(listFormatter)} · 跨${daySpan(planAt, endAt, zone)}天"
        }
    }

    /** 详情/周视图信息弹窗里的文案：`M月d日 HH:mm` 或 `M月d日 HH:mm → M月d日 HH:mm`。 */
    fun rangeLabel(planAt: Long, endAt: Long?): String {
        if (!hasRange(planAt, endAt)) return Dates.toDateTimeText(planAt)
        return "${Dates.toDateTimeText(planAt)} → ${Dates.toDateTimeText(endAt!!)}"
    }

    /**
     * 保存前的校验，返回第一条不合法的说明；全部合法时返回 null。
     *
     * 索引从 1 开始，和编辑界面上的「计划 N」一致。
     */
    fun validate(drafts: List<PlanDraft>): String? {
        val duplicated = drafts.groupBy { it.startAt }.entries.firstOrNull { it.value.size > 1 }
        if (duplicated != null) {
            return "有 ${duplicated.value.size} 个计划的开始时间相同，请调整后再保存"
        }
        drafts.forEachIndexed { index, draft ->
            val end = draft.endAt ?: return@forEachIndexed
            if (end <= draft.startAt) {
                return "第 ${index + 1} 个计划：结束时间要晚于开始时间"
            }
        }
        return null
    }

    private fun localDate(millis: Long, zone: ZoneId): LocalDate =
        Instant.ofEpochMilli(millis).atZone(zone).toLocalDate()

    private fun minuteOfDay(millis: Long, zone: ZoneId): Int {
        val time = Instant.ofEpochMilli(millis).atZone(zone).toLocalTime()
        return time.hour * 60 + time.minute
    }

    private fun clockText(millis: Long, zone: ZoneId): String =
        Instant.ofEpochMilli(millis).atZone(zone).format(clockFormatter)

    private fun clip(segment: PlanSegment, dayStartMinutes: Int, dayEndMinutes: Int): PlanSegment? {
        val start = segment.startMinutes.coerceAtLeast(dayStartMinutes)
        val end = segment.endMinutes.coerceAtMost(dayEndMinutes)
        if (end <= start) return null
        return segment.copy(startMinutes = start, endMinutes = end)
    }
}
