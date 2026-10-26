package com.weeklyplanner.domain

import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.ReminderEntity
import com.weeklyplanner.data.TaskEntity
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

    const val KIND_DUE: String = ReminderEntity.KIND_DUE
    const val KIND_PLAN: String = ReminderEntity.KIND_PLAN
    const val KIND_PLAN_END: String = ReminderEntity.KIND_PLAN_END

    /** 截止提醒：截止日期的前一天，默认 09:00。 */
    fun dueFireAt(dueAt: Long, hour: Int, minute: Int): Long {
        val zone = ZoneId.systemDefault()
        val dueDate = Instant.ofEpochMilli(dueAt).atZone(zone).toLocalDate()
        return dueDate.minusDays(1).atTime(hour, minute).atZone(zone).toInstant().toEpochMilli()
    }

    fun planFireAt(planAt: Long, leadMinutes: Int): Long =
        planAt - leadMinutes.coerceIn(0, 24 * 60).toLong() * 60_000L

    /** 结束提醒：就是结束时间本身，不提前。 */
    fun planEndFireAt(endAt: Long): Long = endAt

    /**
     * 根据任务与计划时间算出期望的提醒集合；已完成的、时间已过期的由调用方过滤。
     *
     * 三个开关互相独立：
     * - 截止：只有 `task.remindDue` 为 true 才有；
     * - 开始：只有 `plan.remindStart` 为 true 才有（沿用设置里的提前分钟数）；
     * - 结束：只有 `plan.endAt != null && plan.remindEnd` 才有，`kind = "plan_end"`。
     */
    fun specs(
        tasks: List<TaskEntity>,
        plans: Map<Long, List<PlanTimeEntity>>,
        settings: AppSettings
    ): List<Spec> {
        val result = mutableListOf<Spec>()
        for (task in tasks) {
            val dueAt = task.dueAt
            if (task.remindDue && dueAt != null) {
                result += Spec(
                    taskId = task.id,
                    kind = KIND_DUE,
                    planKey = 0L,
                    fireAt = dueFireAt(dueAt, settings.reminderHour, settings.reminderMinute),
                    anchorAt = dueAt
                )
            }
            for (plan in plans[task.id].orEmpty()) {
                if (plan.remindStart) {
                    result += Spec(
                        taskId = task.id,
                        kind = KIND_PLAN,
                        planKey = plan.id,
                        fireAt = planFireAt(plan.planAt, settings.planLeadMinutes),
                        anchorAt = plan.planAt
                    )
                }
                val endAt = plan.endAt
                if (endAt != null && plan.remindEnd) {
                    result += Spec(
                        taskId = task.id,
                        kind = KIND_PLAN_END,
                        planKey = plan.id,
                        fireAt = planEndFireAt(endAt),
                        anchorAt = endAt
                    )
                }
            }
        }
        return result
    }
}
