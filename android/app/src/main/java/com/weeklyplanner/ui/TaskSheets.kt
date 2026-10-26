package com.weeklyplanner.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.domain.PlanDraft
import com.weeklyplanner.domain.PlanTimes
import com.weeklyplanner.ui.components.ConfirmDialog
import com.weeklyplanner.ui.components.DatePickerModal
import com.weeklyplanner.ui.components.SegmentedChips
import com.weeklyplanner.ui.components.TimePickerModal
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime

/** 编辑界面上一个计划行里可以被点击修改的字段。 */
private enum class PlanField { START_DATE, START_TIME, END_DATE, END_TIME }

private data class PlanPickTarget(val index: Int, val field: PlanField)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskEditorSheet(
    task: TaskEntity,
    initialPlans: List<PlanDraft>,
    onDismiss: () -> Unit,
    onSave: (TaskEntity, List<PlanDraft>) -> Unit,
    onDelete: (Long) -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var title by remember(task) { mutableStateOf(task.title) }
    var note by remember(task) { mutableStateOf(task.note) }
    var kind by remember(task) { mutableStateOf(task.kind) }
    var priority by remember(task) { mutableStateOf(task.priority) }
    var remindDue by remember(task) { mutableStateOf(task.remindDue) }
    var dueEnabled by remember(task) { mutableStateOf(task.dueAt != null) }
    var dueDate by remember(task) { mutableStateOf(task.dueAt?.let { Dates.toDate(it) } ?: Dates.today()) }
    var dueHour by remember(task) {
        mutableStateOf(task.dueAt?.let { Instant.ofEpochMilli(it).atZone(ZoneId.systemDefault()).hour } ?: 18)
    }
    var dueMinute by remember(task) {
        mutableStateOf(task.dueAt?.let { Instant.ofEpochMilli(it).atZone(ZoneId.systemDefault()).minute } ?: 0)
    }
    var planDrafts by remember(task) { mutableStateOf(initialPlans.sortedBy { it.startAt }) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }

    var showDueDate by remember { mutableStateOf(false) }
    var showDueTime by remember { mutableStateOf(false) }
    var pickTarget by remember { mutableStateOf<PlanPickTarget?>(null) }

    fun updateDraft(index: Int, transform: (PlanDraft) -> PlanDraft) {
        val current = planDrafts.getOrNull(index) ?: return
        planDrafts = planDrafts.toMutableList().also { it[index] = transform(current) }
    }

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
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("提醒截止", style = MaterialTheme.typography.labelLarge)
                        Text(
                            "会在截止前一天提醒你",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Switch(checked = remindDue, onCheckedChange = { remindDue = it })
                }
            }

            Spacer(Modifier.height(14.dp))
            Text("计划时间", style = MaterialTheme.typography.labelLarge)
            Spacer(Modifier.height(4.dp))
            Text(
                "一个任务可以有多个计划时间；可以只填开始，也可以设置结束时间",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            planDrafts.forEachIndexed { index, draft ->
                PlanDraftRow(
                    index = index,
                    draft = draft,
                    onDraftChange = { updated -> updateDraft(index) { updated } },
                    onDelete = { planDrafts = planDrafts.filterIndexed { i, _ -> i != index } },
                    onPickStartDate = { pickTarget = PlanPickTarget(index, PlanField.START_DATE) },
                    onPickStartTime = { pickTarget = PlanPickTarget(index, PlanField.START_TIME) },
                    onPickEndDate = { pickTarget = PlanPickTarget(index, PlanField.END_DATE) },
                    onPickEndTime = { pickTarget = PlanPickTarget(index, PlanField.END_TIME) }
                )
            }
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = {
                // 新计划默认从「现在」开始（23 点后用明天 08:00），结束为空，提醒开始开、结束关。
                planDrafts = planDrafts + PlanDraft(startAt = defaultPlanStartAt())
                error = null
            }) {
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
                        val invalid = PlanTimes.validate(planDrafts)
                        if (invalid != null) {
                            error = invalid
                            return@Button
                        }
                        val dueAt = if (dueEnabled) Dates.atMillis(dueDate, dueHour, dueMinute) else null
                        // 结束时间为空时不允许留下「提醒结束」，避免生成无效提醒。
                        val cleaned = planDrafts.map {
                            if (it.endAt == null) it.copy(remindEnd = false) else it
                        }
                        onSave(
                            task.copy(
                                title = title.trim(),
                                note = note.trim(),
                                kind = kind,
                                priority = priority,
                                dueAt = dueAt,
                                remindDue = remindDue
                            ),
                            cleaned
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

    pickTarget?.let { target ->
        val draft = planDrafts.getOrNull(target.index)
        if (draft != null) {
            val zone = ZoneId.systemDefault()
            when (target.field) {
                PlanField.START_DATE -> DatePickerModal(
                    initial = Dates.toDate(draft.startAt),
                    onDismiss = { pickTarget = null },
                    onPick = { date ->
                        val time = Instant.ofEpochMilli(draft.startAt).atZone(zone).toLocalTime()
                        updateDraft(target.index) {
                            it.copy(startAt = Dates.atMillis(date, time.hour, time.minute))
                        }
                        pickTarget = null
                    }
                )
                PlanField.START_TIME -> TimePickerModal(
                    initialHour = Instant.ofEpochMilli(draft.startAt).atZone(zone).hour,
                    initialMinute = Instant.ofEpochMilli(draft.startAt).atZone(zone).minute,
                    onDismiss = { pickTarget = null }
                ) { h, m ->
                    val date = Dates.toDate(draft.startAt)
                    updateDraft(target.index) {
                        it.copy(startAt = Dates.atMillis(date, h, m))
                    }
                    pickTarget = null
                }
                PlanField.END_DATE -> DatePickerModal(
                    initial = draft.endAt?.let { Dates.toDate(it) } ?: Dates.toDate(draft.startAt),
                    onDismiss = { pickTarget = null },
                    onPick = { date ->
                        val endAt = draft.endAt ?: draft.startAt
                        val time = Instant.ofEpochMilli(endAt).atZone(zone).toLocalTime()
                        updateDraft(target.index) {
                            it.copy(endAt = Dates.atMillis(date, time.hour, time.minute))
                        }
                        pickTarget = null
                    }
                )
                PlanField.END_TIME -> TimePickerModal(
                    initialHour = Instant.ofEpochMilli(draft.endAt ?: draft.startAt).atZone(zone).hour,
                    initialMinute = Instant.ofEpochMilli(draft.endAt ?: draft.startAt).atZone(zone).minute,
                    onDismiss = { pickTarget = null }
                ) { h, m ->
                    val date = draft.endAt?.let { Dates.toDate(it) } ?: Dates.toDate(draft.startAt)
                    updateDraft(target.index) {
                        it.copy(endAt = Dates.atMillis(date, h, m))
                    }
                    pickTarget = null
                }
            }
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

/** 一条计划时间的编辑行：开始日期/时间、结束开关、提醒开关。 */
@Composable
private fun PlanDraftRow(
    index: Int,
    draft: PlanDraft,
    onDraftChange: (PlanDraft) -> Unit,
    onDelete: () -> Unit,
    onPickStartDate: () -> Unit,
    onPickStartTime: () -> Unit,
    onPickEndDate: () -> Unit,
    onPickEndTime: () -> Unit
) {
    val zone = ZoneId.systemDefault()
    val start = Instant.ofEpochMilli(draft.startAt).atZone(zone)
    val end = draft.endAt?.let { Instant.ofEpochMilli(it).atZone(zone) }
    val endTooEarly = end != null && end.toInstant().toEpochMilli() <= draft.startAt

    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.28f))
            .padding(horizontal = 10.dp, vertical = 8.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "计划 ${index + 1}",
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.weight(1f)
            )
            Text(
                "${start.monthValue} 月 ${start.dayOfMonth} 日 ${clockText(start)}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            IconButton(onClick = onDelete) {
                Icon(Icons.Filled.Close, contentDescription = "删除计划时间")
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = onPickStartDate, modifier = Modifier.weight(1f)) {
                Text("${start.monthValue} 月 ${start.dayOfMonth} 日")
            }
            OutlinedButton(onClick = onPickStartTime, modifier = Modifier.weight(1f)) {
                Text(clockText(start))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("设置结束时间", style = MaterialTheme.typography.labelLarge)
                Text(
                    "不设置就只显示开始时间点",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Switch(
                checked = draft.endAt != null,
                onCheckedChange = { on ->
                    onDraftChange(
                        if (on) {
                            draft.copy(endAt = draft.startAt + 60 * 60_000L)
                        } else {
                            draft.copy(endAt = null, remindEnd = false)
                        }
                    )
                }
            )
        }
        if (end != null) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(onClick = onPickEndDate, modifier = Modifier.weight(1f)) {
                    Text("${end.monthValue} 月 ${end.dayOfMonth} 日")
                }
                OutlinedButton(onClick = onPickEndTime, modifier = Modifier.weight(1f)) {
                    Text(clockText(end))
                }
            }
            if (endTooEarly) {
                Text(
                    "结束时间要晚于开始时间",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error
                )
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("提醒开始", style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
            Switch(
                checked = draft.remindStart,
                onCheckedChange = { on -> onDraftChange(draft.copy(remindStart = on)) }
            )
        }
        if (end != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("提醒结束", style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                Switch(
                    checked = draft.remindEnd,
                    onCheckedChange = { on -> onDraftChange(draft.copy(remindEnd = on)) }
                )
            }
        }
    }
}

/** 新增计划的默认开始：现在之后的下一个整半点；23 点后用明天 08:00。 */
private fun defaultPlanStartAt(): Long {
    val now = ZonedDateTime.now(ZoneId.systemDefault())
    if (now.hour >= 23) return Dates.atMillis(Dates.today().plusDays(1), 8, 0)
    val next = ((now.hour * 60 + now.minute) / 30 + 1) * 30
    return Dates.atMillis(Dates.today(), next / 60, next % 60)
}

private fun clockText(time: ZonedDateTime): String = "%02d:%02d".format(time.hour, time.minute)

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
                Text(
                    "截止时间：${Dates.toDateTimeText(due)}" +
                        if (task.remindDue) "（会提醒）" else "（不提醒）",
                    style = MaterialTheme.typography.bodyMedium
                )
            }
            if (plans.isNotEmpty()) {
                Spacer(Modifier.height(14.dp))
                Text("计划时间", style = MaterialTheme.typography.labelLarge)
                plans.sortedBy { it.planAt }.forEach { plan ->
                    Text(
                        "· " + PlanTimes.rangeLabel(plan.planAt, plan.endAt),
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
            onConfirm = { onDelete() },
            onDismiss = { confirmDelete = false }
        )
    }
}
