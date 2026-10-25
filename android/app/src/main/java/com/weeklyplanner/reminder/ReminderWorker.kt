package com.weeklyplanner.reminder

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.weeklyplanner.WeeklyApp

/** 兜底：定期检查漏掉的提醒（不依赖精确闹钟）。 */
class ReminderWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? WeeklyApp ?: return Result.success()
        return try {
            app.scheduleRepository.refreshReminders()
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
