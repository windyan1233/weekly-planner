package com.weeklyplanner.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.ui.components.ConfirmDialog
import com.weeklyplanner.ui.components.DatePickerModal
import com.weeklyplanner.ui.components.SegmentedChips
import com.weeklyplanner.ui.components.TimePickerModal
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskEditorSheet(
    task: TaskEntity,
    initialPlans: List<Long>,
    onDismiss: () -> Unit,
    onSave: (TaskEntity, List<Long>) -> Unit,
    onDelete: (Long) -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var title by remember(task) { mutableStateOf(task.title) }
    var note by remember(task) { mutableStateOf(task.note) }
    var kind by remember(task) { mutableStateOf(task.kind) }
    var priority by remember(task) { mutableStateOf(task.priority) }
    var dueEnabled by remember(task) { mutableStateOf(task.dueAt != null) }
    var dueDate by remember(task) { mutableStateOf(task.dueAt?.let { Dates.toDate(it) } ?: Dates.today()) }
    var dueHour by remember(task) {
        mutableStateOf(task.dueAt?.let { Instant.ofEpochMilli(it).atZone(ZoneId.systemDefault()).hour } ?: 18)
    }
    var dueMinute by remember(task) {
        mutableStateOf(task.dueAt?.let { Instant.ofEpochMilli(it).atZone(ZoneId.systemDefault()).minute } ?: 0)
    }
    var planTimes by remember(task) { mutableStateOf(initialPlans.sorted()) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }

    var showDueDate by remember { mutableStateOf(false) }
    var showDueTime by remember { mutableStateOf(false) }
    var showPlanDate by remember { mutableStateOf(false) }
    var showPlanTime by remember { mutableStateOf(false) }
    var pendingPlanDate by remember { mutableStateOf(LocalDate.now()) }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 28.dp)
        ) {
            Text(
                if (task.id == 0L) "新建任务" else "编辑任务",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(16.dp))
            OutlinedTextField(
                value = title,
                onValueChange = { title = it },
                label = { Text("任务名称") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = note,
                onValueChange = { note = it },
                label = { Text("备注（选填）") },
                minLines = 2,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(14.dp))
            Text("分类", style = MaterialTheme.typography.labelLarge)
            Spacer(Modifier.height(6.dp))
            SegmentedChips(listOf("学习", "工作", "生活"), kind, onSelect = { kind = it })
            Spacer(Modifier.height(12.dp))
            Text("优先级", style = MaterialTheme.typography.labelLarge)
            Spacer(Modifier.height(6.dp))
            SegmentedChips(listOf("普通", "重要", "紧急"), priority, onSelect = { priority = it })

            Spacer(Modifier.height(14.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("截止时间", style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                Switch(checked = dueEnabled, onCheckedChange = { dueEnabled = it })
            }
            if (dueEnabled) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = { showDueDate = true }, modifier = Modifier.weight(1f)) {
                        Text("${dueDate.monthValue} 月 ${dueDate.dayOfMonth} 日")
                    }
                    OutlinedButton(onClick = { showDueTime = true }, modifier = Modifier.weight(1f)) {
                        Text("%02d:%02d".format(dueHour, dueMinute))
                    }
                }
                Text(
                    "会在截止前一天提醒你",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Spacer(Modifier.height(14.dp))
            Text("计划时间", style = MaterialTheme.typography.labelLarge)
            Spacer(Modifier.height(4.dp))
            Text(
                "一个任务可以有多个计划时间，互相独立",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            planTimes.forEach { millis ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(top = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(Dates.toDateTimeText(millis), modifier = Modifier.weight(1f))
                    IconButton(onClick = { planTimes = planTimes - millis }) {
                        Icon(Icons.Filled.Close, contentDescription = "删除计划时间")
                    }
                }
            }
            OutlinedButton(onClick = { showPlanDate = true }) {
                Icon(Icons.Filled.Add, contentDescription = null)
                Spacer(Modifier.width(4.dp))
                Text("添加计划时间")
            }

            if (error != null) {
                Spacer(Modifier.height(10.dp))
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }
            Spacer(Modifier.height(20.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (task.id != 0L) {
                    OutlinedButton(onClick = { confirmDelete = true }, modifier = Modifier.weight(1f)) {
                        Text("删除", color = MaterialTheme.colorScheme.error)
                    }
                }
                Button(
                    onClick = {
                        if (title.isBlank()) {
                            error = "请填写任务名称"
                            return@Button
                        }
                        val dueAt = if (dueEnabled) Dates.atMillis(dueDate, dueHour, dueMinute) else null
                        onSave(
                            task.copy(
                                title = title.trim(),
                                note = note.trim(),
                                kind = kind,
                                priority = priority,
                                dueAt = dueAt
                            ),
                            planTimes
                        )
                    },
                    modifier = Modifier.weight(1.4f)
                ) { Text("保存") }
            }
        }
    }

    if (showDueDate) {
        DatePickerModal(dueDate, onDismiss = { showDueDate = false }, onPick = { dueDate = it })
    }
    if (showDueTime) {
        TimePickerModal(dueHour, dueMinute, onDismiss = { showDueTime = false }) { h, m ->
            dueHour = h
            dueMinute = m
        }
    }
    if (showPlanDate) {
        DatePickerModal(Dates.today(), onDismiss = { showPlanDate = false }, onPick = { date ->
            pendingPlanDate = date
            showPlanDate = false
            showPlanTime = true
        })
    }
    if (showPlanTime) {
        TimePickerModal(8, 0, onDismiss = { showPlanTime = false }) { h, m ->
            planTimes = (planTimes + Dates.atMillis(pendingPlanDate, h, m)).distinct().sorted()
            showPlanTime = false
        }
    }
    if (confirmDelete) {
        ConfirmDialog(
            title = "删除任务",
            text = "删除后，这个任务和它的计划时间、提醒都会一起删除。",
            confirmText = "删除",
            onConfirm = { onDelete(task.id) },
            onDismiss = { confirmDelete = false }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskDetailSheet(
    task: TaskEntity,
    plans: List<PlanTimeEntity>,
    onDismiss: () -> Unit,
    onEdit: () -> Unit,
    onToggle: (Boolean) -> Unit,
    onDelete: () -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var confirmDelete by remember { mutableStateOf(false) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp)
        ) {
            Text(task.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(
                listOf(task.kind, task.priority, if (task.done) "已完成" else "进行中").joinToString(" · "),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (task.note.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Text(task.note, style = MaterialTheme.typography.bodyMedium)
            }
            task.dueAt?.let { due ->
                Spacer(Modifier.height(10.dp))
                Text("截止时间：${Dates.toDateTimeText(due)}", style = MaterialTheme.typography.bodyMedium)
            }
            if (plans.isNotEmpty()) {
                Spacer(Modifier.height(14.dp))
                Text("计划时间", style = MaterialTheme.typography.labelLarge)
                plans.sortedBy { it.planAt }.forEach { plan ->
                    Text(
                        "· " + Dates.toDateTimeText(plan.planAt),
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
            }
            Spacer(Modifier.height(20.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = { onToggle(!task.done) }, modifier = Modifier.weight(1f)) {
                    Text(if (task.done) "恢复未完成" else "标记完成")
                }
                OutlinedButton(onClick = onEdit, modifier = Modifier.weight(1f)) { Text("编辑") }
            }
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = { confirmDelete = true }, modifier = Modifier.fillMaxWidth()) {
                Text("删除任务", color = MaterialTheme.colorScheme.error)
            }
        }
    }
    if (confirmDelete) {
        ConfirmDialog(
            title = "删除任务",
            text = "删除后，这个任务和它的计划时间、提醒都会一起删除。",
            confirmText = "删除",
            onConfirm = onDelete,
            onDismiss = { confirmDelete = false }
        )
    }
}
