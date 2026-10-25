package com.weeklyplanner.ui.screens

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.weeklyplanner.data.CourseEntity
import com.weeklyplanner.data.CourseSessionEntity
import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.ui.components.CardSurface
import com.weeklyplanner.ui.components.EmptyState
import com.weeklyplanner.ui.components.SectionTitle
import java.time.LocalDate
import kotlin.math.abs

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun ScheduleScreen(
    tasks: List<TaskEntity>,
    plans: List<PlanTimeEntity>,
    courseSessions: List<CourseSessionEntity>,
    courses: List<CourseEntity>,
    selectedDate: LocalDate,
    weekStart: LocalDate,
    onSelectDate: (LocalDate) -> Unit,
    onChangeWeek: (Long) -> Unit,
    onToday: () -> Unit,
    onOpenTask: (Long) -> Unit,
    onToggleTask: (TaskEntity, Boolean) -> Unit,
    viewMode: String = "list"
) {
    val today = Dates.today()
    val days = Dates.weekDays(weekStart)
    val tasksById = remember(tasks) { tasks.associateBy { it.id } }
    val coursesById = remember(courses) { courses.associateBy { it.id } }
    val dayCourses = remember(courseSessions, selectedDate) {
        courseSessions.filter { it.day == selectedDate.toString() }.sortedBy { it.startMinutes }
    }

    // 切周时内容从侧边轻轻滑入，避免整屏硬切
    val weekSlide = remember { Animatable(0f) }
    var lastWeekStart by remember { mutableStateOf(weekStart) }
    LaunchedEffect(weekStart) {
        if (weekStart != lastWeekStart) {
            val direction = if (weekStart > lastWeekStart) 1f else -1f
            lastWeekStart = weekStart
            weekSlide.snapTo(direction)
            weekSlide.animateTo(
                0f,
                animationSpec = tween(durationMillis = 240, easing = FastOutSlowInEasing)
            )
        }
    }

    Column(Modifier.fillMaxSize()) {
        val rangeText = "${weekStart.monthValue} 月 ${weekStart.dayOfMonth} 日 - ${weekStart.plusDays(6).monthValue} 月 ${weekStart.plusDays(6).dayOfMonth} 日"
        if (viewMode == "week") {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(start = 20.dp, end = 8.dp, top = 2.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    rangeText,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.weight(1f)
                )
                TextButton(onClick = onToday) { Text("回到本周") }
            }
        } else {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(start = 20.dp, end = 8.dp, top = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("日程", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                    Text(
                        rangeText,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                TextButton(onClick = onToday) { Text("回到本周") }
            }
        }

        if (viewMode == "week") {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Spacer(Modifier.width(36.dp))
                days.forEach { day ->
                    DayCell(
                        modifier = Modifier.weight(1f),
                        date = day,
                        selected = day == selectedDate,
                        today = day == today,
                        onClick = { onSelectDate(day) }
                    )
                }
            }
        } else {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = { onChangeWeek(-1) }) {
                    Icon(Icons.Filled.ChevronLeft, contentDescription = "上一周")
                }
                Row(Modifier.weight(1f)) {
                    days.forEach { day ->
                        DayCell(
                            modifier = Modifier.weight(1f),
                            date = day,
                            selected = day == selectedDate,
                            today = day == today,
                            onClick = { onSelectDate(day) }
                        )
                    }
                }
                IconButton(onClick = { onChangeWeek(1) }) {
                    Icon(Icons.Filled.ChevronRight, contentDescription = "下一周")
                }
            }
        }

        if (viewMode == "week") {
            var weekDragX by remember(weekStart) { mutableFloatStateOf(0f) }
            Box(
                Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        translationX = weekSlide.value * 56.dp.toPx()
                        alpha = 1f - abs(weekSlide.value) * 0.25f
                    }
                    .pointerInput(weekStart) {
                        detectHorizontalDragGestures(
                            onDragStart = { weekDragX = 0f },
                            onHorizontalDrag = { change, amount ->
                                weekDragX += amount
                                change.consume()
                            },
                            onDragEnd = {
                                if (weekDragX > 120) onChangeWeek(-1) else if (weekDragX < -120) onChangeWeek(1)
                                weekDragX = 0f
                            }
                        )
                    }
            ) {
                WeekGridView(
                    tasks = tasks,
                    plans = plans,
                    courseSessions = courseSessions,
                    courses = courses,
                    weekStart = weekStart,
                    selectedDate = selectedDate,
                    onOpenTask = onOpenTask
                )
            }
            return@Column
        }

        var dragX by remember(weekStart) { mutableFloatStateOf(0f) }
        Column(
            Modifier
                .fillMaxSize()
                .graphicsLayer {
                    translationX = weekSlide.value * 56.dp.toPx()
                    alpha = 1f - abs(weekSlide.value) * 0.25f
                }
                .pointerInput(weekStart) {
                    detectHorizontalDragGestures(
                        onDragStart = { dragX = 0f },
                        onHorizontalDrag = { change, amount ->
                            dragX += amount
                            change.consume()
                        },
                        onDragEnd = {
                            if (dragX > 120) onChangeWeek(-1) else if (dragX < -120) onChangeWeek(1)
                            dragX = 0f
                        }
                    )
                }
        ) {
            val planItems = plans
                .filter { Dates.toDate(it.planAt) == selectedDate }
                .sortedBy { it.planAt }
            val dueItems = tasks
                .filter { it.dueAt != null && Dates.toDate(it.dueAt!!) == selectedDate }
                .sortedBy { it.dueAt }
            val overdue = tasks
                .filter { !it.done && it.dueAt != null && Dates.toDate(it.dueAt!!) < today }
                .sortedBy { it.dueAt }
            val plannedIds = plans.map { it.taskId }.toSet()
            val unscheduled = tasks.filter { !it.done && it.dueAt == null && it.id !in plannedIds }

            val empty = planItems.isEmpty() && dueItems.isEmpty() && overdue.isEmpty() &&
                unscheduled.isEmpty() && dayCourses.isEmpty()
            if (empty) {
                EmptyState(
                    title = "这一天还没有安排",
                    subtitle = "点右下角「新建任务」加一条，或左右滑动切换周",
                    modifier = Modifier.fillMaxWidth()
                )
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 96.dp)
                ) {
                    item {
                        val courseMinutes = dayCourses.sumOf { (it.endMinutes - it.startMinutes).coerceAtLeast(0) }
                        val activePlans = planItems.count { plan -> tasksById[plan.taskId]?.done != true }
                        val openDue = dueItems.count { !it.done }
                        CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                            Text(
                                "今日概览",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                buildString {
                                    append("${dayCourses.size} 节课")
                                    if (courseMinutes > 0) {
                                        append("（约 %.1f 小时）".format(courseMinutes / 60.0))
                                    }
                                    append(" · $activePlans 个计划")
                                    append(" · $openDue 个截止")
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                    if (dayCourses.isNotEmpty()) {
                        item { SectionTitle("课程") }
                        items(dayCourses, key = { "course-${it.id}" }) { session ->
                            val course = coursesById[session.courseId] ?: return@items
                            CourseRow(
                                name = course.name,
                                location = course.location,
                                startMinutes = session.startMinutes,
                                endMinutes = session.endMinutes,
                                color = course.color
                            )
                        }
                    }
                    if (planItems.isNotEmpty()) {
                        item { SectionTitle("计划时间") }
                        items(planItems, key = { "plan-${it.id}" }) { plan ->
                            val task = tasksById[plan.taskId] ?: return@items
                            TaskRow(
                                title = task.title,
                                subtitle = listOf(task.kind, task.priority).joinToString(" · "),
                                meta = Dates.toTimeText(plan.planAt),
                                done = task.done,
                                onClick = { onOpenTask(task.id) },
                                onToggle = { onToggleTask(task, it) }
                            )
                        }
                    }
                    if (dueItems.isNotEmpty()) {
                        item { SectionTitle("截止") }
                        items(dueItems, key = { "due-${it.id}" }) { task ->
                            TaskRow(
                                title = task.title,
                                subtitle = "截止 " + (task.dueAt?.let { Dates.toDateTimeText(it) } ?: ""),
                                meta = null,
                                done = task.done,
                                onClick = { onOpenTask(task.id) },
                                onToggle = { onToggleTask(task, it) }
                            )
                        }
                    }
                    if (overdue.isNotEmpty()) {
                        item { SectionTitle("已逾期") }
                        items(overdue, key = { "overdue-${it.id}" }) { task ->
                            TaskRow(
                                title = task.title,
                                subtitle = "已过截止时间",
                                meta = task.dueAt?.let { Dates.toDateTimeText(it) },
                                done = task.done,
                                onClick = { onOpenTask(task.id) },
                                onToggle = { onToggleTask(task, it) },
                                danger = true
                            )
                        }
                    }
                    if (unscheduled.isNotEmpty()) {
                        item { SectionTitle("还没安排时间") }
                        items(unscheduled, key = { "todo-${it.id}" }) { task ->
                            TaskRow(
                                title = task.title,
                                subtitle = task.kind,
                                meta = null,
                                done = task.done,
                                onClick = { onOpenTask(task.id) },
                                onToggle = { onToggleTask(task, it) }
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DayCell(
    modifier: Modifier = Modifier,
    date: LocalDate,
    selected: Boolean,
    today: Boolean,
    onClick: () -> Unit
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            Dates.weekdayLabel(date).removePrefix("周"),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.height(16.dp),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center
        )
        Spacer(Modifier.height(2.dp))
        Box(
            modifier = Modifier
                .size(32.dp)
                .background(
                    when {
                        selected -> MaterialTheme.colorScheme.primary
                        today -> MaterialTheme.colorScheme.primaryContainer
                        else -> Color.Transparent
                    },
                    CircleShape
                ),
            contentAlignment = Alignment.Center
        ) {
            Text(
                date.dayOfMonth.toString(),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = if (selected || today) FontWeight.SemiBold else FontWeight.Normal,
                color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface
            )
        }
    }
}

@Composable
private fun CourseRow(
    name: String,
    location: String,
    startMinutes: Int,
    endMinutes: Int,
    color: String
) {
    val tint = remember(color) {
        try {
            Color(android.graphics.Color.parseColor(color))
        } catch (e: Exception) {
            Color(0xFF6C8AE4)
        }
    }
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .clip(RoundedCornerShape(14.dp)),
        color = MaterialTheme.colorScheme.surface
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier
                    .width(4.dp)
                    .height(34.dp)
                    .background(tint, RoundedCornerShape(2.dp))
            )
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    name,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    location.ifBlank { "地点未填" },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            Text(
                "%02d:%02d-%02d:%02d".format(startMinutes / 60, startMinutes % 60, endMinutes / 60, endMinutes % 60),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun TaskRow(
    title: String,
    subtitle: String,
    meta: String?,
    done: Boolean,
    onClick: () -> Unit,
    onToggle: (Boolean) -> Unit,
    danger: Boolean = false
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .clip(RoundedCornerShape(14.dp)),
        color = MaterialTheme.colorScheme.surface,
        onClick = onClick
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = { onToggle(!done) }, modifier = Modifier.size(36.dp)) {
                Icon(
                    if (done) Icons.Filled.CheckCircle else Icons.Filled.RadioButtonUnchecked,
                    contentDescription = if (done) "已完成" else "未完成",
                    tint = if (done) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline
                )
            }
            Spacer(Modifier.width(6.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (danger) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            if (meta != null) {
                Text(
                    meta,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}
