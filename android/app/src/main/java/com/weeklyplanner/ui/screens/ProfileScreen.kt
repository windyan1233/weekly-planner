package com.weeklyplanner.ui.screens

import android.app.AlarmManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.weeklyplanner.WeeklyApp
import com.weeklyplanner.backup.BackupManager
import com.weeklyplanner.data.AccountEntity
import com.weeklyplanner.domain.AppSettings
import com.weeklyplanner.domain.Categories
import com.weeklyplanner.domain.Category
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.domain.Money
import com.weeklyplanner.ui.components.CardSurface
import com.weeklyplanner.ui.components.ColorDot
import com.weeklyplanner.ui.components.ConfirmDialog
import com.weeklyplanner.ui.components.SegmentedChips
import com.weeklyplanner.ui.components.SectionTitle
import com.weeklyplanner.ui.components.TimePickerModal
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(
    settings: AppSettings,
    accounts: List<AccountEntity>,
    balances: Map<Long, Long>,
    courseCount: Int,
    courseSessionCount: Int,
    onOpenCourseImport: () -> Unit,
    onClearCourses: () -> Unit,
    onAddAccount: (String, Long) -> Unit,
    onRenameAccount: (AccountEntity, String, Long) -> Unit,
    onStartTransfer: () -> Unit,
    onSaveSettings: (AppSettings) -> Unit,
    onMessage: (String) -> Unit,
    onDataImported: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val app = context.applicationContext as WeeklyApp

    var showAddAccount by remember { mutableStateOf(false) }
    var renameTarget by remember { mutableStateOf<AccountEntity?>(null) }
    var showReminderTime by remember { mutableStateOf(false) }
    var importText by remember { mutableStateOf<String?>(null) }
    var confirmClearCourses by remember { mutableStateOf(false) }
    var showAuthorNote by remember { mutableStateOf(false) }
    var showHelp by remember { mutableStateOf(false) }
    var showCategoryDialog by remember { mutableStateOf(false) }
    var editingCategory by remember { mutableStateOf<Category?>(null) }
    var categoryName by remember { mutableStateOf("") }
    val versionName = remember {
        runCatching {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName
        }.getOrNull().orEmpty()
    }

   val notificationGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        ContextCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS) ==
        PackageManager.PERMISSION_GRANTED
    val exactAlarmOk = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        (context.getSystemService(AlarmManager::class.java)).canScheduleExactAlarms()
    } else true

    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        if (uri != null) {
            scope.launch {
                runCatching {
                    val json = BackupManager.exportJson(app)
                    withContext(Dispatchers.IO) {
                        context.contentResolver.openOutputStream(uri)?.use { stream ->
                            stream.write(json.toByteArray(Charsets.UTF_8))
                        }
                    }
                }.onSuccess { onMessage("备份已导出") }
                    .onFailure { onMessage("导出失败：${it.message}") }
            }
        }
    }

    val importLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            scope.launch {
                val text = runCatching {
                    withContext(Dispatchers.IO) {
                        context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                    }
                }.getOrNull()
                if (text.isNullOrBlank()) {
                    onMessage("读取备份文件失败")
                } else {
                    importText = text
                }
            }
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(top = 8.dp, bottom = 96.dp)
    ) {
        item {
            Text(
                "我的",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp)
            )
        }

        item { SectionTitle("资金分区", trailing = { TextButton(onClick = { onStartTransfer() }) { Text("转账") } }) }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                if (accounts.isEmpty()) {
                    Text(
                        "还没有资金分区，先添加一个（例如：饭卡、生活费）",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                } else {
                    accounts.forEach { account ->
                        Surface(
                            color = MaterialTheme.colorScheme.surface,
                            shape = RoundedCornerShape(10.dp),
                            onClick = { renameTarget = account },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(Modifier.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text(account.name, modifier = Modifier.weight(1f))
                                Text(
                                    Money.format(balances[account.id] ?: 0L),
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                        }
                    }
                }
                Spacer(Modifier.height(6.dp))
                OutlinedButton(onClick = { showAddAccount = true }) { Text("添加资金分区") }
            }
        }

        item { SectionTitle("支出分类") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Text(
                    "可自定义名称和颜色；改名不会影响已有流水，删除后旧流水显示为「其他」。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(6.dp))
                settings.categories.forEach { category ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        ColorDot(Color(category.argb))
                        Spacer(Modifier.padding(horizontal = 4.dp))
                        Text(
                            category.label,
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.weight(1f)
                        )
                        TextButton(onClick = {
                            editingCategory = category
                            categoryName = category.label
                            showCategoryDialog = true
                        }) { Text("改名") }
                        TextButton(
                            enabled = settings.categories.size > 1,
                            onClick = {
                                onSaveSettings(
                                    settings.copy(categories = settings.categories - category)
                                )
                                onMessage("已删除分类「" + category.label + "」")
                            }
                        ) { Text("删除") }
                    }
                }
                Row {
                    TextButton(onClick = {
                        editingCategory = null
                        categoryName = ""
                        showCategoryDialog = true
                    }) { Text("添加分类") }
                    TextButton(onClick = {
                        onSaveSettings(settings.copy(categories = Categories.defaults))
                        onMessage("已恢复默认六类")
                    }) { Text("恢复默认") }
                }
            }
        }

        item { SectionTitle("提醒设置") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("截止日前一天提醒时间", modifier = Modifier.weight(1f))
                    TextButton(onClick = { showReminderTime = true }) {
                        Text("%02d:%02d".format(settings.reminderHour, settings.reminderMinute))
                    }
                }
                Spacer(Modifier.height(6.dp))
                Text("计划时间提前提醒", style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(6.dp))
                SegmentedChips(
                    options = listOf("5 分钟", "10 分钟", "15 分钟", "30 分钟"),
                    selected = "${settings.planLeadMinutes} 分钟",
                    onSelect = { label ->
                        val minutes = label.substringBefore(" ").toIntOrNull() ?: 10
                        onSaveSettings(settings.copy(planLeadMinutes = minutes))
                    }
                )
            }
        }

        item { SectionTitle("日程视图") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Text(
                    "周视图像电脑版一样按时间排；列表是现在的卡片列表。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(8.dp))
                SegmentedChips(
                    options = listOf("列表", "周视图"),
                    selected = if (settings.scheduleViewMode == "week") "周视图" else "列表",
                    onSelect = { label ->
                        onSaveSettings(
                            settings.copy(
                                scheduleViewMode = if (label == "周视图") "week" else "list"
                            )
                        )
                    }
                )
            }
        }

        item { SectionTitle("外观") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                SegmentedChips(
                    options = listOf("跟随系统", "浅色", "深色"),
                    selected = when (settings.theme) {
                        "light" -> "浅色"
                        "dark" -> "深色"
                        else -> "跟随系统"
                    },
                    onSelect = { label ->
                        val theme = when (label) {
                            "浅色" -> "light"
                            "深色" -> "dark"
                            else -> "system"
                        }
                        onSaveSettings(settings.copy(theme = theme))
                    }
                )
            }
        }

        item { SectionTitle("权限与后台") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("通知权限", style = MaterialTheme.typography.bodyMedium)
                        Text(
                            if (notificationGranted) "已开启，能收到提醒" else "未开启，提醒不会弹出",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    TextButton(onClick = {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            notificationPermissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            onMessage("当前系统无需单独授权")
                        }
                    }) { Text(if (notificationGranted) "已开启" else "去开启") }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("精确提醒", style = MaterialTheme.typography.bodyMedium)
                        Text(
                            if (exactAlarmOk) "可以准时触发" else "系统限制了精确闹钟，提醒可能延迟",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    TextButton(onClick = {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                            val intent = Intent(
                                Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                                Uri.parse("package:${context.packageName}")
                            )
                            runCatching { context.startActivity(intent) }
                                .onFailure { onMessage("请到系统设置里允许「闹钟和提醒」") }
                        } else {
                            onMessage("当前系统默认允许精确提醒")
                        }
                    }) { Text(if (exactAlarmOk) "已允许" else "去设置") }
                }
            }
        }

        item { SectionTitle("课表") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Text(
                    if (courseCount > 0) "已导入 $courseCount 门课 · $courseSessionCount 次课" else "还没有导入课程表",
                    style = MaterialTheme.typography.bodyMedium
                )
                Text(
                    "支持 .xls / .xlsx / .csv；课程只做展示，不占任务和提醒。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                TextButton(onClick = { showHelp = true }) { Text("课表导入 / 导出说明") }
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(onClick = onOpenCourseImport, modifier = Modifier.weight(1f)) {
                        Text("导入课表")
                    }
                    OutlinedButton(
                        onClick = { confirmClearCourses = true },
                        modifier = Modifier.weight(1f),
                        enabled = courseCount > 0
                    ) { Text("清空课程") }
                }
            }
        }

        item { SectionTitle("数据") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Text(
                    "备份文件包含任务、记账、资金分区和月报；恢复时会整体替换当前数据。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(
                        onClick = { exportLauncher.launch("weekly-planner-backup-${LocalDate.now()}.json") },
                        modifier = Modifier.weight(1f)
                    ) { Text("导出备份") }
                    OutlinedButton(
                        onClick = { importLauncher.launch(arrayOf("*/*")) },
                        modifier = Modifier.weight(1f)
                    ) { Text("恢复备份") }
                }
            }
        }

        item { SectionTitle("关于") }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Text("一周日程 · Android 版", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(4.dp))
                Text(
                    "版本 $versionName",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    "所有数据只保存在本机（Room 数据库），不联网、不需要账号。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = { showHelp = true }) {
                        Text("使用说明")
                    }
                    OutlinedButton(onClick = { showAuthorNote = true }) {
                        Text("作者的话")
                    }
                }
            }
        }
    }

    if (showAuthorNote) {
        AuthorNoteSheet(onDismiss = { showAuthorNote = false })
    }

    if (showHelp) {
        HelpSheet(onDismiss = { showHelp = false })
    }

    if (showAddAccount) {
        AccountDialog(
            title = "添加资金分区",
            initialName = "",
            initialOpening = "0",
            onConfirm = { name, opening ->
                if (name.isBlank()) {
                    onMessage("请填写资金分区名称")
                } else {
                    onAddAccount(name.trim(), opening)
                    showAddAccount = false
                }
            },
            onDismiss = { showAddAccount = false }
        )
    }

    renameTarget?.let { account ->
        AccountDialog(
            title = "编辑资金分区",
            initialName = account.name,
            initialOpening = Money.formatPlain(account.openingCents),
            onConfirm = { name, opening ->
                if (name.isBlank()) {
                    onMessage("名称不能为空")
                } else {
                    onRenameAccount(account, name.trim(), opening)
                    renameTarget = null
                }
            },
            onDismiss = { renameTarget = null }
        )
    }

    if (showCategoryDialog) {
        AlertDialog(
            onDismissRequest = { showCategoryDialog = false },
            title = { Text(if (editingCategory == null) "添加支出分类" else "分类改名") },
            text = {
                OutlinedTextField(
                    value = categoryName,
                    onValueChange = { categoryName = it },
                    label = { Text("名称") },
                    singleLine = true
                )
            },
            confirmButton = {
                TextButton(
                    enabled = categoryName.isNotBlank(),
                    onClick = {
                        val name = categoryName.trim()
                        val list = settings.categories.toMutableList()
                        val target = editingCategory
                        if (target == null) {
                            val palette = listOf(
                                0xFFE57373, 0xFF64B5F6, 0xFF81C784, 0xFFFFB74D,
                                0xFFBA68C8, 0xFF4DB6AC, 0xFFFF8A65, 0xFF9575CD
                            )
                            list.add(
                                Category(
                                    "custom_" + System.currentTimeMillis(),
                                    name,
                                    palette[list.size % palette.size]
                                )
                            )
                        } else {
                            val index = list.indexOfFirst { it.key == target.key }
                            if (index >= 0) list[index] = list[index].copy(label = name)
                        }
                        onSaveSettings(settings.copy(categories = list))
                        showCategoryDialog = false
                    }
                ) { Text("保存") }
            },
            dismissButton = {
                TextButton(onClick = { showCategoryDialog = false }) { Text("取消") }
            }
        )
    }

    if (showReminderTime) {
        TimePickerModal(settings.reminderHour, settings.reminderMinute, onDismiss = { showReminderTime = false }) { h, m ->
            onSaveSettings(settings.copy(reminderHour = h, reminderMinute = m))
        }
    }

    if (confirmClearCourses) {
        ConfirmDialog(
            title = "清空课程表",
            text = "确定删除所有课程和上课记录吗？不会影响任务、提醒和记账。",
            confirmText = "清空",
            onConfirm = {
                onClearCourses()
                confirmClearCourses = false
            },
            onDismiss = { confirmClearCourses = false }
        )
    }

    if (importText != null) {
        ConfirmDialog(
            title = "恢复备份",
            text = "恢复会用备份文件整体替换当前的任务、账目和月报，确定继续吗？",
            confirmText = "恢复",
            onConfirm = {
                val text = importText ?: return@ConfirmDialog
                scope.launch {
                    runCatching { BackupManager.importJson(app, text) }
                        .onSuccess { summary ->
                            onDataImported()
                            onMessage(
                                "恢复完成：${summary["accounts"]} 个资金分区、" +
                                    "${summary["transactions"]} 条账目、" +
                                    "${summary["tasks"]} 个任务"
                            )
                        }
                        .onFailure { onMessage("恢复失败：${it.message}") }
                }
            },
            onDismiss = { importText = null }
        )
    }
}

@Composable
private fun AccountDialog(
    title: String,
    initialName: String,
    initialOpening: String?,
    onConfirm: (String, Long) -> Unit,
    onDismiss: () -> Unit
) {
    var name by remember { mutableStateOf(initialName) }
    var opening by remember { mutableStateOf(initialOpening ?: "") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("名称") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                if (initialOpening != null) {
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = opening,
                        onValueChange = { opening = it },
                        label = { Text("初始余额") },
                        prefix = { Text("¥") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val cents = when {
                    initialOpening == null -> 0L
                    opening.isBlank() -> 0L
                    else -> Money.parseToCents(opening) ?: 0L
                }
                onConfirm(name, cents)
            }) { Text("确定") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } }
    )
}
