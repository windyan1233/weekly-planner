package com.weeklyplanner.reminder

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.weeklyplanner.MainActivity
import com.weeklyplanner.R
import com.weeklyplanner.data.ReminderEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.domain.Dates

object ReminderNotifier {
    const val CHANNEL_ID = "task_reminders"

    fun createChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "任务提醒",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "截止前一天提醒、计划开始 / 结束提醒"
            enableVibration(true)
        }
        manager.createNotificationChannel(channel)
    }

    fun show(context: Context, reminder: ReminderEntity, task: TaskEntity) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(MainActivity.EXTRA_TASK_ID, task.id)
        }
        val contentIntent = PendingIntent.getActivity(
            context,
            task.id.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val text = when (reminder.kind) {
            ReminderEntity.KIND_DUE -> {
                val due = task.dueAt?.let { Dates.toDateTimeText(it) } ?: ""
                "明天截止 · $due"
            }
            ReminderEntity.KIND_PLAN_END -> {
                val end = Dates.toDateTimeText(reminder.anchorAt)
                "计划结束时间 $end 到了"
            }
            else -> {
                val plan = Dates.toDateTimeText(reminder.anchorAt)
                "计划时间 $plan 快到了"
            }
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(task.title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(contentIntent)
            .build()
        try {
            NotificationManagerCompat.from(context).notify(reminder.id.toInt(), notification)
        } catch (e: SecurityException) {
            // 没有通知权限时静默跳过
        }
    }
}
