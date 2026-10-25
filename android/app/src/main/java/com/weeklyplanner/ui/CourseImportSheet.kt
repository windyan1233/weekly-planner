package com.weeklyplanner.ui

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.weeklyplanner.courses.FlatCsvParser
import com.weeklyplanner.courses.ParseError
import com.weeklyplanner.courses.ParseResult
import com.weeklyplanner.courses.TimetableParser
import com.weeklyplanner.courses.TimetableReader
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.ui.components.DatePickerModal
import com.weeklyplanner.ui.components.SegmentedChips
import com.weeklyplanner.ui.components.TimePickerModal
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters
import java.time.DayOfWeek

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CourseImportSheet(
    initialStart: LocalDate,
    onDismiss: () -> Unit,
    onImport: (ParseResult, LocalDate) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    var fileName by remember { mutableStateOf("") }
    var parsed by remember { mutableStateOf<ParseResult?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var startDate by remember { mutableStateOf(initialStart) }
    var showDate by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var useCustomTimes by remember { mutableStateOf(false) }
    var customTimes by remember { mutableStateOf(TimetableParser.defaultSectionTimes) }
    var editingSection by remember { mutableStateOf<Int?>(null) }
    var editingStart by remember { mutableStateOf(true) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            busy = true
            error = null
            runCatching {
                withContext(Dispatchers.IO) {
                    val name = displayName(context, uri) ?: "课表文件"
                    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                        ?: throw ParseError("读取文件失败")
                    val rows = TimetableReader.readRows(name, bytes)
                    val result = if (FlatCsvParser.isGrid(rows)) {
                        TimetableParser.parse(rows)
                    } else {
                        FlatCsvParser.parse(rows)
                    }
                    name to result
                }
            }.onSuccess { pair ->
                fileName = pair.first
                parsed = pair.second
                useCustomTimes = !pair.second.hasTimetableTimes
            }.onFailure { e ->
                error = e.message ?: "解析失败"
                parsed = null
            }
            busy = false
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 26.dp)
        ) {
            Text("导入课表", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(
                "支持教务系统导出的 .xls / .xlsx，也支持 .csv。PDF 请先转成 CSV 或 Excel。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(Modifier.height(14.dp))
            Button(
                onClick = {
                    picker.launch(
                        arrayOf(
                            "application/vnd.ms-excel",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "text/csv",
                            "text/comma-separated-values",
                            "*/*"
                        )
                    )
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text("选择课表文件") }

            if (fileName.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Text(fileName, style = MaterialTheme.typography.bodyMedium)
            }
            if (busy) {
                Spacer(Modifier.height(12.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.height(18.dp))
                    Spacer(Modifier.height(6.dp))
                    Text("  正在解析…", style = MaterialTheme.typography.bodySmall)
                }
            }
            error?.let {
                Spacer(Modifier.height(10.dp))
                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            }

            parsed?.let { result ->
                Spacer(Modifier.height(14.dp))
                Text(
                    "共 ${result.courses.size} 条课程安排 · ${result.sessionCount} 次课",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold
                )
                if (result.warnings.isNotEmpty()) {
                    Text(
                        result.warnings.take(3).joinToString("\n"),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("第 1 周的星期一", modifier = Modifier.weight(1f))
                    OutlinedButton(onClick = { showDate = true }) {
                        Text("${startDate.year}-${"%02d".format(startDate.monthValue)}-${"%02d".format(startDate.dayOfMonth)}")
                    }
                }
                Text(
                    "按周次把每节课展开到具体日期；填错会导致日期整体偏移。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(10.dp))
                Text("课程时间", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                if (!result.hasTimetableTimes) {
                    Text(
                        "课表里没有节次时间，请自己设置每节课的起止时间后再导入。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
                Spacer(Modifier.height(6.dp))
                SegmentedChips(
                    options = listOf("使用课表时间", "自定义每节时间"),
                    selected = if (useCustomTimes) "自定义每节时间" else "使用课表时间",
                    onSelect = { label ->
                        if (label == "自定义每节时间") {
                            useCustomTimes = true
                        } else if (result.hasTimetableTimes) {
                            useCustomTimes = false
                        }
                    }
                )
                if (useCustomTimes) {
                    Spacer(Modifier.height(4.dp))
                    TimetableParser.sectionPeriods.forEachIndexed { index, periods ->
                        val times = customTimes[index]
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .padding(vertical = 2.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                "第 ${periods.first()}-${periods.last()} 节",
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.weight(1f)
                            )
                            OutlinedButton(onClick = {
                                editingSection = index
                                editingStart = true
                            }) { Text(formatTime(times.first)) }
                            Spacer(Modifier.width(6.dp))
                            OutlinedButton(onClick = {
                                editingSection = index
                                editingStart = false
                            }) { Text(formatTime(times.second)) }
                        }
                    }
                }

                val previewCourses = if (useCustomTimes) {
                    val map = buildMap {
                        customTimes.forEachIndexed { index, times ->
                            TimetableParser.sectionPeriods[index].forEach { put(it, times) }
                        }
                    }
                    TimetableParser.applyTimes(result.courses, map)
                } else {
                    result.courses
                }
                Spacer(Modifier.height(8.dp))
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 260.dp)
                ) {
                    LazyColumn(Modifier.padding(vertical = 4.dp)) {
                        items(previewCourses) { course ->
                            Row(Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                                Text(
                                    Dates.weekdayLabel(startDate.plusDays(course.weekday.toLong())),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.width(44.dp)
                                )
                                Column(Modifier.weight(1f)) {
                                    Text(course.name, style = MaterialTheme.typography.bodyMedium)
                                    Text(
                                        listOf(
                                            formatTime(course.startMinutes),
                                            course.location,
                                            course.teacher
                                        ).filter { it.isNotBlank() }.joinToString(" · "),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    }
                }
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        val finalResult = if (useCustomTimes) {
                            val map = buildMap {
                                customTimes.forEachIndexed { index, times ->
                                    TimetableParser.sectionPeriods[index].forEach { put(it, times) }
                                }
                            }
                            result.copy(
                                courses = TimetableParser.applyTimes(result.courses, map),
                                hasTimetableTimes = true
                            )
                        } else {
                            result
                        }
                        onImport(finalResult, startDate)
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text("导入到日程") }
            }
        }
    }

    if (showDate) {
        DatePickerModal(startDate, onDismiss = { showDate = false }, onPick = { startDate = it })
    }

    editingSection?.let { index ->
        val times = customTimes[index]
        val initial = if (editingStart) times.first else times.second
        TimePickerModal(
            initialHour = initial / 60,
            initialMinute = initial % 60,
            onDismiss = { editingSection = null }
        ) { hour, minute ->
            val minutes = hour * 60 + minute
            val updated = customTimes.toMutableList()
            val current = updated[index]
            updated[index] = if (editingStart) minutes to current.second else current.first to minutes
            customTimes = updated
            editingSection = null
        }
    }
}

private fun formatTime(minutes: Int): String =
    "%02d:%02d".format(minutes / 60, minutes % 60)

private fun displayName(context: Context, uri: Uri): String? {
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0) return cursor.getString(index)
        }
    }
    return uri.lastPathSegment
}

fun defaultSemesterStart(): LocalDate {
    val today = Dates.today()
    return today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
}
