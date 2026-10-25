package com.weeklyplanner.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.weeklyplanner.WeeklyApp
import com.weeklyplanner.backup.BackupManager
import com.weeklyplanner.courses.ParseResult
import com.weeklyplanner.data.AccountEntity
import com.weeklyplanner.data.CourseRepository
import com.weeklyplanner.data.CourseSessionEntity
import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.data.TransactionEntity
import com.weeklyplanner.domain.AppSettings
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.domain.MonthFigures
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate

class MainViewModel(private val app: WeeklyApp) : ViewModel() {
    private val scheduleRepository = app.scheduleRepository
    private val financeRepository = app.financeRepository
    private val settingsRepository = app.settingsRepository
    private val database = app.database

    var tab by mutableStateOf(0)
    var selectedDate by mutableStateOf(Dates.today())
    var weekStart by mutableStateOf(Dates.startOfWeek(Dates.today()))
    var monthKey by mutableStateOf(Dates.monthKey(Dates.today()))

    var openTaskId by mutableStateOf<Long?>(null)
    var editorTask by mutableStateOf<TaskEntity?>(null)
    var editorPlans by mutableStateOf<List<Long>>(emptyList())
    var showQuickAdd by mutableStateOf(false)
    var quickAddType by mutableStateOf(TransactionEntity.TYPE_EXPENSE)
    var quickAddEditing by mutableStateOf<TransactionEntity?>(null)
    var showTransfer by mutableStateOf(false)
    var showAccountDialog by mutableStateOf(false)
    var message by mutableStateOf<String?>(null)

    var balances by mutableStateOf<Map<Long, Long>>(emptyMap())
    var report by mutableStateOf<MonthFigures?>(null)
    var refreshToken by mutableStateOf(0)
    var courseSessions by mutableStateOf<List<com.weeklyplanner.data.CourseSessionEntity>>(emptyList())
    var courseStats by mutableStateOf(0 to 0)
    var showCourseImport by mutableStateOf(false)
    var pendingImportText by mutableStateOf<String?>(null)

    val tasks = scheduleRepository.tasks.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val plans = scheduleRepository.plans.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val accounts = financeRepository.accounts.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val transactions = financeRepository.allTransactions.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val reports = financeRepository.reports.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val settings = settingsRepository.observe().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AppSettings())
    private val courseRepository = CourseRepository(app.database)
    val courses = courseRepository.courses.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        refreshBalances()
        loadReport()
        refreshCourses()
        viewModelScope.launch {
            courseStats = courseRepository.stats()
        }
    }

    // ---------------------------------------------------------------- 日程
    fun selectDate(date: LocalDate) {
        selectedDate = date
        weekStart = Dates.startOfWeek(date)
        refreshCourses()
    }

    fun changeWeek(delta: Long) {
        weekStart = weekStart.plusWeeks(delta)
        selectedDate = weekStart
        refreshCourses()
    }

    fun goToday() {
        val today = Dates.today()
        weekStart = Dates.startOfWeek(today)
        selectedDate = today
        refreshCourses()
    }

    fun refreshCourses() {
        viewModelScope.launch {
            courseSessions = courseRepository.sessionsBetween(weekStart, weekStart.plusDays(6))
        }
    }

    fun openCourseImport() {
        showCourseImport = true
    }

    fun closeCourseImport() {
        showCourseImport = false
    }

    fun importCourses(result: ParseResult, semesterStart: LocalDate) {
        viewModelScope.launch {
            val stats = courseRepository.import(result, semesterStart)
            courseStats = stats
            settingsRepository.update(settings.value.copy(courseSemesterStart = semesterStart.toString()))
            showCourseImport = false
            refreshCourses()
            message = "课表已导入：${stats.first} 门课 / ${stats.second} 次课"
        }
    }

    fun clearCourses() {
        viewModelScope.launch {
            courseRepository.clear()
            courseStats = 0 to 0
            courseSessions = emptyList()
            message = "课程表已清空"
        }
    }

    fun openTask(id: Long) {
        tab = 0
        openTaskId = id
    }

    fun dismissTask() {
        openTaskId = null
    }

    fun startNewTask() {
        editorTask = TaskEntity(title = "")
        editorPlans = emptyList()
    }

    fun editTask(task: TaskEntity) {
        val plans = plans.value.filter { it.taskId == task.id }.map { it.planAt }
        editorTask = task
        editorPlans = plans
        openTaskId = null
    }

    fun closeEditor() {
        editorTask = null
        editorPlans = emptyList()
    }

    fun saveTask(task: TaskEntity, planTimes: List<Long>) {
        viewModelScope.launch {
            val saved = task.copy(updatedAt = System.currentTimeMillis())
            scheduleRepository.saveTask(
                saved,
                planTimes.sorted().map { PlanTimeEntity(taskId = task.id, planAt = it) }
            )
            closeEditor()
            openTaskId = null
            message = "已保存"
        }
    }

    fun deleteTask(id: Long) {
        viewModelScope.launch {
            scheduleRepository.deleteTask(id)
            openTaskId = null
            closeEditor()
            message = "已删除任务"
        }
    }

    fun toggleTask(task: TaskEntity, done: Boolean) {
        viewModelScope.launch { scheduleRepository.setDone(task.id, done) }
    }

    // ---------------------------------------------------------------- 记账
    fun setMonth(key: String) {
        monthKey = key
        loadReport()
    }

    fun refreshBalances() {
        viewModelScope.launch { balances = financeRepository.accountBalances() }
    }

    fun loadReport() {
        viewModelScope.launch {
            report = financeRepository.monthFigures(monthKey)
        }
    }

    fun addTransaction(
        type: String,
        amountCents: Long,
        categoryKey: String,
        accountId: Long,
        title: String,
        note: String,
        occurredAt: Long
    ) {
        viewModelScope.launch {
            financeRepository.addTransaction(type, amountCents, categoryKey, accountId, title, note, occurredAt)
            refreshBalances()
            loadReport()
            message = if (type == TransactionEntity.TYPE_INCOME) "已记一笔收入" else "已记一笔支出"
        }
    }

    fun deleteTransaction(id: Long) {
        viewModelScope.launch {
            financeRepository.deleteTransaction(id)
            refreshBalances()
            loadReport()
            message = "已删除账目"
        }
    }

    fun updateTransaction(transaction: TransactionEntity) {
        viewModelScope.launch {
            financeRepository.updateTransaction(transaction)
            refreshBalances()
            loadReport()
            message = "已保存修改"
        }
    }

    fun saveReportSnapshot() {
        viewModelScope.launch {
            financeRepository.ensureReport(monthKey)
            message = "本月报表快照已保存"
        }
    }

    fun addTransfer(fromId: Long, toId: Long, amountCents: Long, note: String, occurredAt: Long) {
        viewModelScope.launch {
            financeRepository.addTransfer(fromId, toId, amountCents, note, occurredAt)
            refreshBalances()
            message = "已转账"
        }
    }

    fun addAccount(name: String, openingCents: Long) {
        viewModelScope.launch {
            financeRepository.addAccount(name, openingCents)
            refreshBalances()
            message = "已添加资金分区"
        }
    }

    fun startQuickAdd(type: String = TransactionEntity.TYPE_EXPENSE) {
        quickAddType = type
        quickAddEditing = null
        showQuickAdd = true
    }

    fun editTransaction(transaction: TransactionEntity) {
        quickAddType = transaction.type
        quickAddEditing = transaction
        showQuickAdd = true
    }

    fun closeQuickAdd() {
        showQuickAdd = false
        quickAddEditing = null
    }

    fun saveAccount(account: AccountEntity, name: String, openingCents: Long) {
        viewModelScope.launch {
            financeRepository.saveAccount(account, name, openingCents)
            refreshBalances()
            message = "已保存资金分区"
        }
    }

    fun saveSettings(settings: AppSettings) {
        viewModelScope.launch { settingsRepository.update(settings) }
    }

    fun clearMessage() {
        message = null
    }

    fun showMessage(text: String) {
        message = text
    }

    fun onDataImported() {
        refreshBalances()
        loadReport()
        message = "数据已恢复"
    }

    /** 从「用其他应用打开」收到的 JSON 文本。 */
    fun offerImport(text: String) {
        pendingImportText = text
    }

    fun dismissImport() {
        pendingImportText = null
    }

    fun confirmImport() {
        val text = pendingImportText ?: return
        viewModelScope.launch {
            runCatching { BackupManager.importJson(app, text) }
                .onSuccess { summary ->
                    refreshBalances()
                    loadReport()
                    refreshCourses()
                    viewModelScope.launch { courseStats = courseRepository.stats() }
                    message = "已导入 ${summary["tasks"]} 个任务、" +
                        "${summary["accounts"]} 个资金分区、" +
                        "${summary["transactions"]} 条账目"
                }
                .onFailure { message = "导入失败：${it.message}" }
            pendingImportText = null
        }
    }

    class Factory(private val app: WeeklyApp) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = MainViewModel(app) as T
    }
}
