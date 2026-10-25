package com.weeklyplanner.domain

import java.time.Instant
import java.time.ZoneId

data class AppSettings(
    val reminderHour: Int = 9,
    val reminderMinute: Int = 0,
    val planLeadMinutes: Int = 10,
    val theme: String = "system",
    val courseSemesterStart: String = "",
    val scheduleViewMode: String = "week",
    val categories: List<Category> = Categories.defaults
) {
    companion object {
        const val KEY_REMINDER_HOUR = "reminder_hour"
        const val KEY_REMINDER_MINUTE = "reminder_minute"
        const val KEY_PLAN_LEAD = "plan_lead_minutes"
        const val KEY_THEME = "theme"
        const val KEY_COURSE_START = "course_semester_start"
        const val KEY_SCHEDULE_VIEW = "schedule_view_mode"
        const val KEY_CATEGORIES = "expense_categories"
    }
}

object ReminderPlanner {
    data class Spec(
        val taskId: Long,
        val kind: String,
        val planKey: Long,
        val fireAt: Long,
        val anchorAt: Long
    )

    const val GRACE_MILLIS: Long = 6 * 60 * 60 * 1000L

    /** 截止提醒：截止日期的前一天，默认 09:00。 */
    fun dueFireAt(dueAt: Long, hour: Int, minute: Int): Long {
        val zone = ZoneId.systemDefault()
        val dueDate = Instant.ofEpochMilli(dueAt).atZone(zone).toLocalDate()
        return dueDate.minusDays(1).atTime(hour, minute).atZone(zone).toInstant().toEpochMilli()
    }

    fun planFireAt(planAt: Long, leadMinutes: Int): Long =
        planAt - leadMinutes.coerceIn(0, 24 * 60).toLong() * 60_000L

    /** 根据任务与计划时间算出期望的提醒集合；已完成的、时间已过期的由调用方过滤。 */
    fun specs(
        tasks: List<Pair<Long, Long?>>, // taskId, dueAt
        plans: Map<Long, List<Pair<Long, Long>>>, // taskId -> (planId, planAt)
        settings: AppSettings
    ): List<Spec> {
        val result = mutableListOf<Spec>()
        for ((taskId, dueAt) in tasks) {
            if (dueAt != null) {
                result += Spec(
                    taskId = taskId,
                    kind = "due",
                    planKey = 0L,
                    fireAt = dueFireAt(dueAt, settings.reminderHour, settings.reminderMinute),
                    anchorAt = dueAt
                )
            }
            plans[taskId].orEmpty().forEach { (planId, planAt) ->
                result += Spec(
                    taskId = taskId,
                    kind = "plan",
                    planKey = planId,
                    fireAt = planFireAt(planAt, settings.planLeadMinutes),
                    anchorAt = planAt
                )
            }
        }
        return result
    }
}
