package com.weeklyplanner.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.weeklyplanner.data.CourseEntity
import com.weeklyplanner.data.CourseSessionEntity
import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.domain.PlanTimes
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.temporal.ChronoUnit

private const val START_HOUR = 7
private const val END_HOUR = 23
private val HOUR_HEIGHT: Dp = 64.dp
private val TIME_COLUMN_WIDTH: Dp = 36.dp
private const val OVERLAP_OFFSET_DP = 6f
private const val MAX_OVERLAP_LEVEL = 3

/** 任务块带一点透明度，压在课程上面时还能看到下面的课。 */
private const val TASK_BLOCK_ALPHA = 0.78f
private const val TASK_BLOCK_DONE_ALPHA = 0.52f

/** 跨天计划在中间那天画的延续条高度。 */
private val CONTINUATION_HEIGHT: Dp = 12.dp

internal data class WeekBlock(
    val dayIndex: Int,
    val startMinutes: Int,
    val endMinutes: Int,
    val title: String,
    val subtitle: String,
    val color: Color,
    val taskId: Long? = null,
    val info: String = "",
    val location: String = "",
    /** 跨天计划在中间那天只画一条细的延续条，不是真实区间。 */
    val continuation: Boolean = false
)

internal data class PlacedBlock(val block: WeekBlock, val level: Int)

/** 重叠的块不切成窄列，而是按层级横向错开，后画的在上层。 */
internal fun placeBlocks(blocks: List<WeekBlock>): List<PlacedBlock> {
    val sorted = blocks.sortedWith(compareBy({ it.startMinutes }, { it.endMinutes }))
    val active = mutableListOf<WeekBlock>()
    val placed = mutableListOf<PlacedBlock>()
    for (block in sorted) {
        active.removeAll { it.endMinutes <= block.startMinutes }
        placed += PlacedBlock(block, active.size.coerceAtMost(MAX_OVERLAP_LEVEL))
        active += block
    }
    return placed
}

private data class DueMarker(
    val dayIndex: Int,
    val minutes: Int,
    val taskId: Long,
    val done: Boolean
)

@Composable
fun WeekGridView(
    tasks: List<TaskEntity>,
    plans: List<PlanTimeEntity>,
    courseSessions: List<CourseSessionEntity>,
    courses: List<CourseEntity>,
    weekStart: LocalDate,
    selectedDate: LocalDate,
    onOpenTask: (Long) -> Unit
) {
    val scheme = MaterialTheme.colorScheme
    val days = remember(weekStart) { Dates.weekDays(weekStart) }
    val tasksById = remember(tasks) { tasks.associateBy { it.id } }
    val coursesById = remember(courses) { courses.associateBy { it.id } }
    var infoBlock by remember { mutableStateOf<WeekBlock?>(null) }
    val scrollState = rememberScrollState()
    val density = LocalDensity.current

    fun priorityColor(task: TaskEntity): Color = when (task.priority) {
        "紧急" -> scheme.error
        "重要" -> scheme.tertiary
        else -> scheme.primary
    }

    // 课程在下、任务在上；任务块不缩窄，靠透明度和层级区分。
    val blocks = buildList {
        for (session in courseSessions) {
            val date = runCatching { LocalDate.parse(session.day) }.getOrNull() ?: continue
            val dayIndex = ChronoUnit.DAYS.between(weekStart, date).toInt()
            if (dayIndex !in 0..6) continue
            val course = coursesById[session.courseId] ?: continue
            val timeText = timeLabel(session.startMinutes, session.endMinutes)
            add(
                WeekBlock(
                    dayIndex = dayIndex,
                    startMinutes = session.startMinutes,
                    endMinutes = session.endMinutes,
                    title = course.name,
                    subtitle = timeText,
                    color = parseColor(course.color),
                    info = listOf(course.name, timeText, course.location, course.teacher)
                        .filter { it.isNotBlank() }.joinToString("\n"),
                    location = course.location
                )
            )
        }
        for (plan in plans) {
            val task = tasksById[plan.taskId] ?: continue
            val blockColor = priorityColor(task).copy(
                alpha = if (task.done) TASK_BLOCK_DONE_ALPHA else TASK_BLOCK_ALPHA
            )
            val info = listOf(
                task.title,
                task.kind,
                task.priority,
                PlanTimes.rangeLabel(plan.planAt, plan.endAt)
            ).filter { it.isNotBlank() }.joinToString("\n")
            val hasRange = PlanTimes.hasRange(plan.planAt, plan.endAt)
            // 只画落在本周内的片段；跨天时开始/结束/中间天各自不同。
            for (segment in PlanTimes.segments(
                planAt = plan.planAt,
                endAt = plan.endAt,
                weekStart = weekStart,
                dayStartMinutes = START_HOUR * 60,
                dayEndMinutes = END_HOUR * 60
            )) {
                val dayIndex = ChronoUnit.DAYS.between(weekStart, segment.date).toInt()
                if (dayIndex !in 0..6) continue
                if (segment.continuation) {
                    add(
                        WeekBlock(
                            dayIndex = dayIndex,
                            startMinutes = segment.startMinutes,
                            endMinutes = segment.endMinutes,
                            title = task.title,
                            subtitle = "跨天延续",
                            color = blockColor,
                            taskId = task.id,
                            info = info,
                            continuation = true
                        )
                    )
                } else {
                    add(
                        WeekBlock(
                            dayIndex = dayIndex,
                            startMinutes = segment.startMinutes,
                            endMinutes = segment.endMinutes,
                            title = task.title,
                            subtitle = if (hasRange) {
                                timeLabel(segment.startMinutes, segment.endMinutes)
                            } else {
                                // 没有结束时间的旧计划：保留原来的「只显示开始时间」。
                                startClock(segment.startMinutes)
                            },
                            color = blockColor,
                            taskId = task.id,
                            info = info
                        )
                    )
                }
            }
        }
    }

    val dueMarkers = buildList {
        for (task in tasks) {
            val due = task.dueAt ?: continue
            val zoned = Instant.ofEpochMilli(due).atZone(ZoneId.systemDefault())
            val dayIndex = ChronoUnit.DAYS.between(weekStart, zoned.toLocalDate()).toInt()
            if (dayIndex !in 0..6) continue
            add(DueMarker(dayIndex, zoned.hour * 60 + zoned.minute, task.id, task.done))
        }
    }

    LaunchedEffect(Unit) {
        val hour = LocalTime.now().hour
        val target = (hour - START_HOUR).coerceIn(0, END_HOUR - START_HOUR - 1)
        scrollState.scrollTo(with(density) { (HOUR_HEIGHT * target.toFloat()).roundToPx() })
    }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(bottom = 120.dp)
    ) {
        val totalHeight = HOUR_HEIGHT * (END_HOUR - START_HOUR).toFloat()
        Row(Modifier.fillMaxWidth().height(totalHeight)) {
            Box(Modifier.width(TIME_COLUMN_WIDTH).fillMaxHeight()) {
                for (hour in START_HOUR..END_HOUR) {
                    Text(
                        "%02d:00".format(hour),
                        modifier = Modifier.offset(
                            y = HOUR_HEIGHT * (hour - START_HOUR).toFloat() - 6.dp
                        ),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 9.sp
                    )
                }
            }
            days.forEachIndexed { dayIndex, date ->
                BoxWithConstraints(
                    Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .padding(horizontal = 1.dp)
                ) {
                    if (date == selectedDate) {
                        Box(Modifier.fillMaxSize().background(scheme.primary.copy(alpha = 0.06f)))
                    }
                    Canvas(Modifier.fillMaxSize()) {
                        val hourPx = HOUR_HEIGHT.toPx()
                        for (hour in START_HOUR..END_HOUR) {
                            val y = hourPx * (hour - START_HOUR)
                            drawLine(
                                color = scheme.outlineVariant.copy(alpha = 0.35f),
                                start = Offset(0f, y),
                                end = Offset(size.width, y),
                                strokeWidth = 1f
                            )
                        }
                    }

                    val placed = placeBlocks(
                        blocks.filter { it.dayIndex == dayIndex && !it.continuation }
                    )
                    // 课程在下、任务在上；任务不缩窄，避免和下面的课程糊在一起。
                    placed.sortedWith(
                        compareBy({ it.block.taskId != null }, { it.block.startMinutes })
                    ).forEach { item ->
                        val top = HOUR_HEIGHT * ((item.block.startMinutes - START_HOUR * 60) / 60f)
                        val height = (HOUR_HEIGHT * ((item.block.endMinutes - item.block.startMinutes) / 60f))
                            .coerceAtLeast(18.dp)
                        val isTask = item.block.taskId != null
                        val shape = RoundedCornerShape(6.dp)
                        Box(
                            Modifier
                                .offset(x = 0.dp, y = top)
                                .width((maxWidth - 1.dp).coerceAtLeast(10.dp))
                                .height(height)
                                .clip(shape)
                                .background(item.block.color)
                                .then(
                                    if (isTask) {
                                        Modifier.border(1.dp, Color.White.copy(alpha = 0.45f), shape)
                                    } else {
                                        Modifier
                                    }
                                )
                                .clickable {
                                    val taskId = item.block.taskId
                                    if (taskId != null) onOpenTask(taskId) else infoBlock = item.block
                                }
                                .padding(horizontal = 1.dp, vertical = 1.dp)
                        ) {
                            Column {
                                Text(
                                    item.block.title,
                                    style = MaterialTheme.typography.labelSmall,
                                    fontWeight = FontWeight.SemiBold,
                                    color = Color.White,
                                    fontSize = 8.sp,
                                    lineHeight = 9.sp,
                                    maxLines = 3,
                                    overflow = TextOverflow.Ellipsis
                                )
                                Text(
                                    item.block.subtitle,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color.White.copy(alpha = 0.88f),
                                    fontSize = 6.5.sp,
                                    lineHeight = 7.5.sp,
                                    maxLines = 1,
                                    softWrap = false,
                                    overflow = TextOverflow.Ellipsis
                                )
                                if (item.block.location.isNotBlank() && height > 66.dp) {
                                    Text(
                                        item.block.location,
                                        style = MaterialTheme.typography.labelSmall,
                                        color = Color.White.copy(alpha = 0.75f),
                                        fontSize = 6.5.sp,
                                        lineHeight = 7.5.sp,
                                        maxLines = 1,
                                        softWrap = false,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                }
                            }
                        }
                    }

                    // 跨天计划在中间那天：一条细的延续条（12:00），低透明度、可点击。
                    blocks.filter { it.dayIndex == dayIndex && it.continuation }.forEach { bar ->
                        val top = HOUR_HEIGHT * ((bar.startMinutes - START_HOUR * 60) / 60f)
                        Row(
                            Modifier
                                .offset(y = top)
                                .fillMaxWidth()
                                .height(CONTINUATION_HEIGHT)
                                .padding(horizontal = 1.dp)
                                .clip(RoundedCornerShape(4.dp))
                                .background(bar.color.copy(alpha = 0.30f))
                                .clickable {
                                    bar.taskId?.let(onOpenTask)
                                }
                                .padding(horizontal = 3.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                Modifier
                                    .size(3.dp)
                                    .background(bar.color.copy(alpha = 0.9f), CircleShape)
                            )
                            Spacer(Modifier.width(3.dp))
                            Text(
                                bar.title,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 6.5.sp,
                                lineHeight = 8.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }

                    // 截止用细线覆盖在块上，不参与泳道，避免把课程挤偏。
                    dueMarkers.filter { it.dayIndex == dayIndex }.forEach { marker ->
                        val top = HOUR_HEIGHT * ((marker.minutes - START_HOUR * 60) / 60f)
                        Row(
                            Modifier
                                .offset(y = top)
                                .fillMaxWidth()
                                .height(10.dp)
                                .clickable { onOpenTask(marker.taskId) }
                                .padding(end = 1.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                Modifier
                                    .weight(1f)
                                    .height(1.dp)
                                    .background(scheme.error.copy(alpha = if (marker.done) 0.4f else 0.9f))
                            )
                            Box(
                                Modifier
                                    .size(5.dp)
                                    .background(
                                        scheme.error.copy(alpha = if (marker.done) 0.4f else 0.9f),
                                        RoundedCornerShape(50)
                                    )
                            )
                        }
                    }
                }
            }
        }
    }

    infoBlock?.let { block ->
        AlertDialog(
            onDismissRequest = { infoBlock = null },
            title = { Text(block.title) },
            text = { Text(block.info) },
            confirmButton = {
                TextButton(onClick = { infoBlock = null }) { Text("关闭") }
            }
        )
    }
}

private fun startClock(minutes: Int): String =
    "%d:%02d".format(minutes / 60, minutes % 60)

private fun timeLabel(startMinutes: Int, endMinutes: Int): String =
    "%d:%02d-%d:%02d".format(
        startMinutes / 60, startMinutes % 60,
        endMinutes / 60, endMinutes % 60
    )

private fun parseColor(value: String): Color = try {
    Color(android.graphics.Color.parseColor(value))
} catch (e: Exception) {
    Color(0xFF6C8AE4)
}
