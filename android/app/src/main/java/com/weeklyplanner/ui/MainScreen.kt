package com.weeklyplanner.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.weeklyplanner.ui.components.ConfirmDialog
import com.weeklyplanner.ui.screens.FinanceScreen
import com.weeklyplanner.ui.screens.ProfileScreen
import com.weeklyplanner.ui.screens.ReportScreen
import com.weeklyplanner.ui.screens.ScheduleScreen
import java.time.LocalDate

@Composable
fun MainScreen(vm: MainViewModel) {
    val tasks by vm.tasks.collectAsStateWithLifecycle()
    val plans by vm.plans.collectAsStateWithLifecycle()
    val accounts by vm.accounts.collectAsStateWithLifecycle()
    val transactions by vm.transactions.collectAsStateWithLifecycle()
    val reports by vm.reports.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val courses by vm.courses.collectAsStateWithLifecycle()

    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(vm.message) {
        vm.message?.let { text ->
            snackbarHostState.showSnackbar(text)
            vm.clearMessage()
        }
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = vm.tab == 0,
                    onClick = { vm.tab = 0 },
                    icon = { Icon(Icons.Filled.CalendarMonth, contentDescription = null) },
                    label = { Text("日程") }
                )
                NavigationBarItem(
                    selected = vm.tab == 1,
                    onClick = { vm.tab = 1 },
                    icon = { Icon(Icons.Filled.AccountBalanceWallet, contentDescription = null) },
                    label = { Text("记账") }
                )
                NavigationBarItem(
                    selected = vm.tab == 2,
                    onClick = { vm.tab = 2 },
                    icon = { Icon(Icons.Filled.BarChart, contentDescription = null) },
                    label = { Text("月报") }
                )
                NavigationBarItem(
                    selected = vm.tab == 3,
                    onClick = { vm.tab = 3 },
                    icon = { Icon(Icons.Filled.Person, contentDescription = null) },
                    label = { Text("我的") }
                )
            }
        },
        floatingActionButton = {
            when (vm.tab) {
                0 -> ExtendedFloatingActionButton(
                    onClick = { vm.startNewTask() },
                    icon = { Icon(Icons.Filled.Add, contentDescription = null) },
                    text = { Text("新建任务") }
                )
                1 -> ExtendedFloatingActionButton(
                    onClick = { vm.startQuickAdd() },
                    icon = { Icon(Icons.Filled.Add, contentDescription = null) },
                    text = { Text("记一笔") }
                )
            }
        }
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (vm.tab) {
                0 -> ScheduleScreen(
                    tasks = tasks,
                    plans = plans,
                    courseSessions = vm.courseSessions,
                    courses = courses,
                    selectedDate = vm.selectedDate,
                    weekStart = vm.weekStart,
                    onSelectDate = vm::selectDate,
                    onChangeWeek = vm::changeWeek,
                    onToday = vm::goToday,
                    onOpenTask = vm::openTask,
                    onToggleTask = vm::toggleTask,
                    viewMode = settings.scheduleViewMode
                )
                1 -> FinanceScreen(
                    categories = settings.categories,
                    accounts = accounts,
                    transactions = transactions,
                    balances = vm.balances,
                    monthKey = vm.monthKey,
                    onMonthChange = vm::setMonth,
                    onEditTransaction = vm::editTransaction,
                    onDeleteTransaction = vm::deleteTransaction
                )
                2 -> ReportScreen(
                    categories = settings.categories,
                    report = vm.report,
                    reports = reports,
                    monthKey = vm.monthKey,
                    onMonthChange = vm::setMonth,
                    onSaveSnapshot = vm::saveReportSnapshot
                )
                else -> ProfileScreen(
                    settings = settings,
                    accounts = accounts,
                    balances = vm.balances,
                    courseCount = vm.courseStats.first,
                    courseSessionCount = vm.courseStats.second,
                    onOpenCourseImport = vm::openCourseImport,
                    onClearCourses = vm::clearCourses,
                    onAddAccount = vm::addAccount,
                    onRenameAccount = vm::saveAccount,
                    onStartTransfer = { vm.startQuickAdd("transfer") },
                    onSaveSettings = vm::saveSettings,
                    onMessage = vm::showMessage,
                    onDataImported = vm::onDataImported
                )
            }
        }
    }

    vm.editorTask?.let { task ->
        TaskEditorSheet(
            task = task,
            initialPlans = vm.editorPlans,
            onDismiss = vm::closeEditor,
            onSave = vm::saveTask,
            onDelete = vm::deleteTask
        )
    }

    val openTask = vm.openTaskId?.let { id -> tasks.firstOrNull { it.id == id } }
    if (openTask != null) {
        TaskDetailSheet(
            task = openTask,
            plans = plans.filter { it.taskId == openTask.id },
            onDismiss = vm::dismissTask,
            onEdit = { vm.editTask(openTask) },
            onToggle = { done -> vm.toggleTask(openTask, done) },
            onDelete = { vm.deleteTask(openTask.id) }
        )
    }

    if (vm.showCourseImport) {
        val storedStart = settings.courseSemesterStart.takeIf { it.isNotBlank() }
            ?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
            ?: defaultSemesterStart()
        CourseImportSheet(
            initialStart = storedStart,
            onDismiss = vm::closeCourseImport,
            onImport = vm::importCourses
        )
    }

    vm.pendingImportText?.let {
        ConfirmDialog(
            title = "导入外部 JSON",
            text = "检测到从其他应用打开的 JSON 备份。导入会整体替换当前的任务、课程、账目和月报，是否继续？",
            confirmText = "导入",
            onConfirm = vm::confirmImport,
            onDismiss = vm::dismissImport
        )
    }

    if (vm.showQuickAdd) {
        QuickAddSheet(
            categories = settings.categories,
            accounts = accounts,
            editing = vm.quickAddEditing,
            initialType = vm.quickAddType,
            onDismiss = vm::closeQuickAdd,
            onSave = { type, cents, category, accountId, title, note, occurredAt ->
                vm.addTransaction(type, cents, category, accountId, title, note, occurredAt)
                vm.closeQuickAdd()
            },
            onUpdate = { transaction ->
                vm.updateTransaction(transaction)
                vm.closeQuickAdd()
            },
            onTransfer = { from, to, cents, note, occurredAt ->
                vm.addTransfer(from, to, cents, note, occurredAt)
                vm.closeQuickAdd()
            }
        )
    }
}
