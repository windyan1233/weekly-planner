package com.weeklyplanner.data

import androidx.room.withTransaction
import com.weeklyplanner.domain.AppSettings
import com.weeklyplanner.domain.Categories
import com.weeklyplanner.domain.FinanceCalculator
import com.weeklyplanner.domain.MonthFigures
import com.weeklyplanner.domain.ReminderPlanner
import com.weeklyplanner.reminder.ReminderScheduler
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map

class SettingsRepository(private val dao: SettingsDao) {
    fun observe(): Flow<AppSettings> = dao.observeAll().map { rows ->
        val map = rows.associate { it.key to it.value }
        AppSettings(
            reminderHour = map[AppSettings.KEY_REMINDER_HOUR]?.toIntOrNull() ?: 9,
            reminderMinute = map[AppSettings.KEY_REMINDER_MINUTE]?.toIntOrNull() ?: 0,
            planLeadMinutes = map[AppSettings.KEY_PLAN_LEAD]?.toIntOrNull() ?: 10,
            theme = map[AppSettings.KEY_THEME] ?: "system",
            courseSemesterStart = map[AppSettings.KEY_COURSE_START] ?: "",
            scheduleViewMode = map[AppSettings.KEY_SCHEDULE_VIEW] ?: "week",
            categories = Categories.decode(map[AppSettings.KEY_CATEGORIES])
        )
    }

    suspend fun load(): AppSettings {
        val map = dao.allRows().associate { it.key to it.value }
        return AppSettings(
            reminderHour = map[AppSettings.KEY_REMINDER_HOUR]?.toIntOrNull() ?: 9,
            reminderMinute = map[AppSettings.KEY_REMINDER_MINUTE]?.toIntOrNull() ?: 0,
            planLeadMinutes = map[AppSettings.KEY_PLAN_LEAD]?.toIntOrNull() ?: 10,
            theme = map[AppSettings.KEY_THEME] ?: "system",
            courseSemesterStart = map[AppSettings.KEY_COURSE_START] ?: "",
            scheduleViewMode = map[AppSettings.KEY_SCHEDULE_VIEW] ?: "week",
            categories = Categories.decode(map[AppSettings.KEY_CATEGORIES])
        )
    }

    suspend fun update(settings: AppSettings) {
        dao.set(SettingEntity(AppSettings.KEY_REMINDER_HOUR, settings.reminderHour.toString()))
        dao.set(SettingEntity(AppSettings.KEY_REMINDER_MINUTE, settings.reminderMinute.toString()))
        dao.set(SettingEntity(AppSettings.KEY_PLAN_LEAD, settings.planLeadMinutes.toString()))
        dao.set(SettingEntity(AppSettings.KEY_THEME, settings.theme))
        dao.set(SettingEntity(AppSettings.KEY_COURSE_START, settings.courseSemesterStart))
        dao.set(SettingEntity(AppSettings.KEY_SCHEDULE_VIEW, settings.scheduleViewMode))
        dao.set(SettingEntity(AppSettings.KEY_CATEGORIES, Categories.encode(settings.categories)))
    }
}

class ScheduleRepository(
    private val db: AppDatabase,
    private val settingsRepository: SettingsRepository,
    private val scheduler: ReminderScheduler
) {
    private val taskDao = db.taskDao()
    private val reminderDao = db.reminderDao()

    val tasks: Flow<List<TaskEntity>> = taskDao.observeAll()
    val plans: Flow<List<PlanTimeEntity>> = taskDao.observeAllPlans()

    fun plansBetween(start: Long, end: Long): Flow<List<PlanTimeEntity>> =
        taskDao.observePlansBetween(start, end)

    fun pendingReminders(): Flow<List<ReminderEntity>> = reminderDao.observePending()

    suspend fun saveTask(task: TaskEntity, plans: List<PlanTimeEntity>): Long {
        val id = taskDao.saveTask(task, plans)
        refreshReminders()
        return id
    }

    suspend fun deleteTask(id: Long) {
        taskDao.deleteTask(id)
        reminderDao.deleteForTask(id)
        refreshReminders()
    }

    suspend fun setDone(id: Long, done: Boolean) {
        taskDao.setDone(id, done)
        refreshReminders()
    }

    suspend fun refreshReminders() {
        val settings = settingsRepository.load()
        val tasks = taskDao.all().filter { !it.done }
        val plansByTask = taskDao.allPlans().groupBy { it.taskId }
        // 三个开关（截止 / 开始 / 结束）都在 ReminderPlanner 里判断；
        // 关掉的开关不会出现在 desired 里，下面会删掉对应的旧提醒。
        val specs = ReminderPlanner.specs(tasks, plansByTask, settings)
        val now = System.currentTimeMillis()

        val desired = specs.associateBy { it.taskId to Triple(it.kind, it.planKey, it.anchorAt) }
        val pending = reminderDao.pending()
        for (reminder in pending) {
            val key = reminder.taskId to Triple(reminder.kind, reminder.planKey, reminder.anchorAt)
            val spec = desired[key]
            if (spec == null || spec.fireAt != reminder.fireAt) {
                reminderDao.delete(reminder.id)
                scheduler.cancel(reminder.id)
            }
        }

        val existing = reminderDao.all().associateBy {
            it.taskId to Triple(it.kind, it.planKey, it.anchorAt)
        }
        for (spec in specs) {
            val key = spec.taskId to Triple(spec.kind, spec.planKey, spec.anchorAt)
            val cached = existing[key]
            if (cached != null && cached.status != ReminderEntity.STATUS_PENDING) continue
            if (spec.fireAt < now - ReminderPlanner.GRACE_MILLIS) continue
            val id = cached?.id ?: reminderDao.insert(
                ReminderEntity(
                    taskId = spec.taskId,
                    kind = spec.kind,
                    planKey = spec.planKey,
                    fireAt = spec.fireAt,
                    anchorAt = spec.anchorAt
                )
            )
            if (id <= 0L) continue
            if (spec.fireAt > now) {
                scheduler.schedule(id, spec.fireAt)
            } else {
                scheduler.fireNow(id)
            }
        }
    }

    suspend fun snooze(reminderId: Long, minutes: Int = 10) {
        val reminder = reminderDao.get(reminderId) ?: return
        val next = System.currentTimeMillis() + minutes * 60_000L
        val id = reminderDao.insert(
            reminder.copy(id = 0L, fireAt = next, status = ReminderEntity.STATUS_PENDING, snoozeCount = reminder.snoozeCount + 1)
        )
        if (id > 0L) scheduler.schedule(id, next)
    }

    suspend fun clearAllReminders() {
        reminderDao.clear()
        scheduler.cancelAll()
    }
}

class FinanceRepository(private val db: AppDatabase) {
    private val financeDao = db.financeDao()

    val accounts: Flow<List<AccountEntity>> = financeDao.observeAccounts()
    val allTransactions: Flow<List<TransactionEntity>> = financeDao.observeAllTransactions()
    val reports: Flow<List<MonthlyReportEntity>> = financeDao.observeReports()

    fun transactionsBetween(start: Long, end: Long): Flow<List<TransactionEntity>> =
        financeDao.observeTransactions(start, end)

    fun transfersBetween(start: Long, end: Long): Flow<List<TransferEntity>> =
        financeDao.observeTransfers(start, end)

    suspend fun accountBalances(): Map<Long, Long> {
        val accounts = financeDao.accounts()
        return accounts.associate { account ->
            account.id to FinanceCalculator.accountBalance(
                openingCents = account.openingCents,
                incomeCents = financeDao.incomeFor(account.id),
                expenseCents = financeDao.expenseFor(account.id),
                transfersOutCents = financeDao.transfersOut(account.id),
                transfersInCents = financeDao.transfersIn(account.id)
            )
        }
    }

    suspend fun totalBalance(): Long = accountBalances().values.sum()

    suspend fun addAccount(name: String, openingCents: Long): Long =
        financeDao.insertAccount(AccountEntity(name = name, openingCents = openingCents, sortOrder = financeDao.accounts().size))

    suspend fun renameAccount(account: AccountEntity, name: String) =
        financeDao.updateAccount(account.copy(name = name))

    suspend fun saveAccount(account: AccountEntity, name: String, openingCents: Long) =
        financeDao.updateAccount(account.copy(name = name.trim(), openingCents = openingCents))

    suspend fun addTransaction(
        type: String,
        amountCents: Long,
        categoryKey: String,
        accountId: Long,
        title: String,
        note: String,
        occurredAt: Long
    ): Long = financeDao.insertTransaction(
        TransactionEntity(
            type = type,
            amountCents = amountCents,
            categoryKey = categoryKey,
            accountId = accountId,
            title = title,
            note = note,
            occurredAt = occurredAt
        )
    )

    suspend fun deleteTransaction(id: Long) = financeDao.deleteTransaction(id)

    suspend fun updateTransaction(transaction: TransactionEntity) = financeDao.updateTransaction(transaction)

    suspend fun addTransfer(fromId: Long, toId: Long, amountCents: Long, note: String, occurredAt: Long): Long =
        financeDao.insertTransfer(
            TransferEntity(
                fromAccountId = fromId,
                toAccountId = toId,
                amountCents = amountCents,
                note = note,
                occurredAt = occurredAt
            )
        )

    suspend fun monthFigures(month: String): MonthFigures {
        val start = com.weeklyplanner.domain.Dates.parseMonthKey(month).atStartOfDay()
            .atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
        val end = com.weeklyplanner.domain.Dates.parseMonthKey(month).plusMonths(1).atStartOfDay()
            .atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
        val transactions = financeDao.transactionsBetween(start, end)
        val opening = financeDao.accounts().sumOf { it.openingCents }
        return FinanceCalculator.monthFigures(
            month = month,
            openingBalanceCents = opening,
            incomeBeforeCents = financeDao.incomeBefore(start),
            expenseBeforeCents = financeDao.expenseBefore(start),
            monthTransactions = transactions
        )
    }

    suspend fun ensureReport(month: String): MonthlyReportEntity {
        financeDao.report(month)?.let { return it }
        val figures = monthFigures(month)
        val report = MonthlyReportEntity(
            month = month,
            incomeCents = figures.incomeCents,
            expenseCents = figures.expenseCents,
            openingCents = figures.openingCents,
            closingCents = figures.closingCents,
            categoryJson = org.json.JSONObject(figures.categories).toString()
        )
        financeDao.saveReport(report)
        return report
    }
}
