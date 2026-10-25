package com.weeklyplanner.reminder

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.weeklyplanner.WeeklyApp
import kotlinx.coroutines.launch

/** 开机、应用更新、修改时间/时区后：重新安排全部提醒。 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action !in setOf(
                Intent.ACTION_BOOT_COMPLETED,
                Intent.ACTION_MY_PACKAGE_REPLACED,
                Intent.ACTION_TIME_CHANGED,
                Intent.ACTION_TIMEZONE_CHANGED
            )
        ) {
            return
        }
        val app = context.applicationContext as? WeeklyApp ?: return
        val result = goAsync()
        app.applicationScope.launch {
            try {
                app.scheduleRepository.refreshReminders()
            } finally {
                result.finish()
            }
        }
    }
}
