package com.weeklyplanner.reminder

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.weeklyplanner.WeeklyApp
import com.weeklyplanner.data.ReminderEntity
import kotlinx.coroutines.launch

/** AlarmManager 到点触发：显示通知并标记已发送。 */
class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val reminderId = intent.getLongExtra(EXTRA_REMINDER_ID, -1L)
        if (reminderId <= 0L) return
        val app = context.applicationContext as? WeeklyApp ?: return
        val result = goAsync()
        app.applicationScope.launch {
            try {
                val reminder = app.database.reminderDao().get(reminderId) ?: return@launch
                if (reminder.status != ReminderEntity.STATUS_PENDING) return@launch
                val task = app.database.taskDao().get(reminder.taskId)
                if (task != null && !task.done) {
                    ReminderNotifier.show(context, reminder, task)
                    app.database.reminderDao().setStatus(reminderId, ReminderEntity.STATUS_SENT)
                } else {
                    app.database.reminderDao().setStatus(reminderId, ReminderEntity.STATUS_MISSED)
                }
            } finally {
                result.finish()
            }
        }
    }

    companion object {
        const val EXTRA_REMINDER_ID = "reminder_id"
    }
}
