package com.weeklyplanner

import android.app.Application
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.weeklyplanner.data.AppDatabase
import com.weeklyplanner.data.FinanceRepository
import com.weeklyplanner.data.ScheduleRepository
import com.weeklyplanner.data.SettingsRepository
import com.weeklyplanner.reminder.ReminderNotifier
import com.weeklyplanner.reminder.ReminderScheduler
import com.weeklyplanner.reminder.ReminderWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit

class WeeklyApp : Application() {
    val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    lateinit var database: AppDatabase
        private set
    lateinit var settingsRepository: SettingsRepository
        private set
    lateinit var scheduleRepository: ScheduleRepository
        private set
    lateinit var financeRepository: FinanceRepository
        private set
    lateinit var reminderScheduler: ReminderScheduler
        private set

    override fun onCreate() {
        super.onCreate()
        database = AppDatabase.get(this)
        settingsRepository = SettingsRepository(database.settingsDao())
        reminderScheduler = ReminderScheduler(this)
        scheduleRepository = ScheduleRepository(database, settingsRepository, reminderScheduler)
        financeRepository = FinanceRepository(database)

        ReminderNotifier.createChannel(this)

        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "reminder-catch-up",
            ExistingPeriodicWorkPolicy.UPDATE,
            PeriodicWorkRequestBuilder<ReminderWorker>(6, TimeUnit.HOURS).build()
        )

        applicationScope.launch {
            try {
                if (database.financeDao().accounts().isEmpty()) {
                    database.financeDao().insertAccount(
                        com.weeklyplanner.data.AccountEntity(name = "现金", openingCents = 0L, sortOrder = 0)
                    )
                }
                scheduleRepository.refreshReminders()
            } catch (e: Exception) {
                // 首次启动数据库还未准备好时忽略，界面操作会再次刷新
            }
        }
    }
}
