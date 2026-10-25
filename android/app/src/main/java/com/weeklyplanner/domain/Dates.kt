package com.weeklyplanner.domain

import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.TemporalAdjusters

object Dates {
    private val zone: ZoneId get() = ZoneId.systemDefault()
    val monthFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM")
    val dayFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("M月d日")
    val weekdayLabels = listOf("周一", "周二", "周三", "周四", "周五", "周六", "周日")

    fun today(): LocalDate = LocalDate.now(zone)

    fun startOfWeek(date: LocalDate): LocalDate =
        date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))

    fun weekDays(weekStart: LocalDate): List<LocalDate> =
        (0..6).map { weekStart.plusDays(it.toLong()) }

    fun startOfMonth(date: LocalDate): LocalDate = date.withDayOfMonth(1)

    fun endOfMonthExclusive(date: LocalDate): LocalDate =
        startOfMonth(date).plusMonths(1)

    fun monthKey(date: LocalDate): String = date.format(monthFormatter)

    fun parseMonthKey(key: String): LocalDate = LocalDate.parse(key + "-01")

    fun atMillis(date: LocalDate, hour: Int, minute: Int): Long =
        date.atTime(LocalTime.of(hour, minute)).atZone(zone).toInstant().toEpochMilli()

    fun startOfDayMillis(date: LocalDate): Long = atMillis(date, 0, 0)

    fun endOfDayMillis(date: LocalDate): Long = atMillis(date.plusDays(1), 0, 0)

    fun toDate(millis: Long): LocalDate =
        Instant.ofEpochMilli(millis).atZone(zone).toLocalDate()

    fun toTimeText(millis: Long): String =
        Instant.ofEpochMilli(millis).atZone(zone).toLocalTime()
            .format(DateTimeFormatter.ofPattern("HH:mm"))

    fun toDateTimeText(millis: Long): String =
        Instant.ofEpochMilli(millis).atZone(zone).toLocalDateTime()
            .format(DateTimeFormatter.ofPattern("M月d日 HH:mm"))

    fun weekdayLabel(date: LocalDate): String = weekdayLabels[date.dayOfWeek.value - 1]

    fun monthLabel(key: String): String {
        val date = parseMonthKey(key)
        return "${date.year} 年 ${date.monthValue} 月"
    }

    fun dayLabel(date: LocalDate): String = "${date.monthValue}月${date.dayOfMonth}日 ${weekdayLabel(date)}"
}
