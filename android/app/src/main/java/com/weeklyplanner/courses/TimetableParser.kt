package com.weeklyplanner.courses

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters

data class ParsedCourse(
    val name: String,
    val teacher: String,
    val location: String,
    val descriptor: String,
    val weekday: Int, // 0 = 周一
    val weeks: List<Int>,
    val periods: List<Int>,
    val startMinutes: Int,
    val endMinutes: Int,
    val raw: String = ""
)

data class ParsedSession(
    val course: ParsedCourse,
    val day: LocalDate,
    val startMinutes: Int,
    val endMinutes: Int
)

class ParseError(message: String) : Exception(message)

data class ParseResult(
    val courses: List<ParsedCourse>,
    val warnings: List<String> = emptyList(),
    /** 课表文件里是否写了大节时间；没有时导入前要让用户自己设置 */
    val hasTimetableTimes: Boolean = true
) {
    val sessionCount: Int get() = courses.sumOf { it.weeks.size }
}

object TimetableParser {
    val weekdayNames = listOf("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

    /** 八大节的默认作息，课表没写时间时使用 */
    val sectionPeriods: List<List<Int>> = listOf(
        listOf(1, 2), listOf(3, 4), listOf(5, 6), listOf(7, 8),
        listOf(9, 10), listOf(11, 12), listOf(13, 14), listOf(15, 16)
    )
    val defaultSectionTimes: List<Pair<Int, Int>> = listOf(
        8 * 60 + 30 to 10 * 60 + 5,
        10 * 60 + 25 to 12 * 60,
        13 * 60 + 30 to 15 * 60 + 5,
        15 * 60 + 25 to 17 * 60,
        18 * 60 to 19 * 60 + 40,
        19 * 60 + 50 to 21 * 60 + 30,
        21 * 60 + 40 to 22 * 60 + 45,
        22 * 60 + 50 to 23 * 60 + 55
    )
    val defaultPeriodTimes: Map<Int, Pair<Int, Int>> = buildMap {
        sectionPeriods.forEachIndexed { index, periods ->
            val times = defaultSectionTimes[index]
            periods.forEach { put(it, times) }
        }
    }
    private val timeRegex = Regex("""(\d{1,2})[:：](\d{2})\s*[-~—]\s*(\d{1,2})[:：](\d{2})""")
    private val periodListRegex = Regex("""\((\d{1,2})\s*[,，]\s*(\d{1,2})\)""")
    private val altPeriodListRegex = Regex("""第\s*(\d{1,2})\s*[-~—]\s*(\d{1,2})\s*节""")
    private val weekOnlyRegex = Regex("""^\s*[\d,，、\-–—~]+\s*[\(（]?\s*\[?\s*周\s*\]?\s*[\)）]?\s*$""")
    private val periodOnlyRegex = Regex("""^\s*\[\s*[\d\-－,，]+\s*节?\]\s*节?\s*$""")
    private val scheduleRegex = Regex("""([\d,\-]+)\s*\(\[周\]\)""")
    private val scheduleAltRegex = Regex("""([\d,\-]+)\s*周""")
    private val periodsRegex = Regex("""\[([\d\-－,，]+)\s*节?\]\s*节?""")

    fun parse(rows: List<List<String>>): ParseResult {
        val table = rows.map { row -> row.map { it.trim() } }
        val headerIndex = table.indexOfFirst { row ->
            row.count { cell -> weekdayNames.any { cell.contains(it) } } >= 5
        }
        if (headerIndex < 0) {
            throw ParseError("没有找到「星期一…星期日」表头，不是课表文件。")
        }
        val header = table[headerIndex]
        val columns = weekdayNames.map { name ->
            header.indexOfFirst { it.contains(name) }
        }
        val periodTimes = mutableMapOf<Int, Pair<Int, Int>>()
        val entries = mutableListOf<ParsedCourse>()
        val seen = mutableSetOf<String>()
        val warnings = mutableListOf<String>()
        var hasTimetableTimes = false

        for (row in table.drop(headerIndex + 1)) {
            val label = row.firstOrNull().orEmpty()
            val periodMatch = periodListRegex.find(label)
                ?: altPeriodListRegex.find(label)
                ?: continue
            val periods = listOf(
                periodMatch.groupValues[1].toInt(),
                periodMatch.groupValues[2].toInt()
            )
            val time = timeRegex.find(label)
            val start: Int
            val end: Int
            if (time != null) {
                hasTimetableTimes = true
                start = time.groupValues[1].toInt() * 60 + time.groupValues[2].toInt()
                end = time.groupValues[3].toInt() * 60 + time.groupValues[4].toInt()
            } else {
                val mapped = periods.mapNotNull { defaultPeriodTimes[it] }
                if (mapped.isEmpty()) {
                    warnings += "第 ${periods.first()}-${periods.last()} 节没有时间，已跳过"
                    continue
                }
                start = mapped.minOf { it.first }
                end = mapped.maxOf { it.second }
            }
            periods.forEach { periodTimes[it] = start to end }
            val rowCourses = mutableListOf<ParsedCourse>()
            columns.forEachIndexed { weekday, column ->
                if (column < 0 || column >= row.size) return@forEachIndexed
                val cell = row[column]
                if (cell.isBlank()) return@forEachIndexed
                parseCell(cell, weekday, start, end, periodTimes) { course, error ->
                    if (course != null) {
                        rowCourses += course
                    } else if (error != null) {
                        warnings += error
                    }
                }
            }
            for (course in rowCourses) {
                val globalKey = listOf(
                    course.name, course.teacher, course.location,
                    course.weekday, course.weeks, course.periods
                ).joinToString("|")
                if (seen.add(globalKey)) entries += course
            }
        }
        if (entries.isEmpty()) throw ParseError("没有解析出任何课程。")
        return ParseResult(
            entries.sortedWith(compareBy({ it.weekday }, { it.startMinutes }, { it.name })),
            warnings,
            hasTimetableTimes = hasTimetableTimes
        )
    }

    /** 用用户设置或课表里的节次时间，重算每门课的起止时间。 */
    fun applyTimes(
        courses: List<ParsedCourse>,
        periodTimes: Map<Int, Pair<Int, Int>>
    ): List<ParsedCourse> = courses.map { course ->
        val mapped = course.periods.mapNotNull { periodTimes[it] }
        if (mapped.isEmpty()) {
            course
        } else {
            course.copy(
                startMinutes = mapped.minOf { it.first },
                endMinutes = mapped.maxOf { it.second }
            )
        }
    }

    private fun mergeSplitSchedule(lines: List<String>): List<String> {
        val result = lines.toMutableList()
        for (index in result.indices) {
            if (!periodOnlyRegex.matches(result[index])) continue
            for (previous in index - 1 downTo 0) {
                if (result[previous].isBlank()) break
                if (weekOnlyRegex.matches(result[previous])) {
                    result[previous] = result[previous].trimEnd() + result[index].trim()
                    result[index] = ""
                    break
                }
            }
        }
        return result
    }

    private fun parseCell(
        cell: String,
        weekday: Int,
        sectionStart: Int,
        sectionEnd: Int,
        periodTimes: MutableMap<Int, Pair<Int, Int>>,
        onCourse: (ParsedCourse?, String?) -> Unit
    ) {
        val blocks = mutableListOf<MutableList<String>>()
        val current = mutableListOf<String>()
        for (line in mergeSplitSchedule(cell.replace("\r", "").split("\n"))) {
            if (line.isBlank()) {
                if (current.isNotEmpty()) {
                    blocks += current.toMutableList()
                    current.clear()
                }
            } else {
                current += line.trim()
            }
        }
        if (current.isNotEmpty()) blocks += current

        val merged = mutableListOf<List<String>>()
        var pendingName: List<String>? = null
        for (block in blocks) {
            val hasSchedule = block.any { scheduleRegex.containsMatchIn(it) || it.contains("周]") }
            if (!hasSchedule) {
                pendingName = (pendingName ?: emptyList()) + block
                continue
            }
            val lines = (pendingName ?: emptyList()) + block
            pendingName = null
            merged += lines
        }

        for (lines in merged) {
            val cleaned = lines.filter { it.isNotBlank() }
            if (cleaned.isEmpty()) continue
            val first = lines.first()
            if (first.contains("周]") || first.contains("[周]")) continue
            val scheduleLine = lines.firstOrNull { scheduleRegex.containsMatchIn(it) || it.contains("周]") }
            if (scheduleLine == null) continue
            val weeks = parseWeeks(scheduleLine)
            if (weeks.isEmpty()) {
                onCourse(null, "跳过（周次无法识别）：$first")
                continue
            }
            val periods = periodsRegex.find(scheduleLine)?.groupValues?.get(1)
                ?.split("-")?.mapNotNull { it.trim().toIntOrNull() }?.filter { it > 0 }
                ?.toList().orEmpty()
            if (periods.isEmpty()) {
                onCourse(null, "跳过（节次无法识别）：$first")
                continue
            }
            val times = periods.mapNotNull { periodTimes[it] }
            val start = times.minOfOrNull { it.first } ?: sectionStart
            val end = times.maxOfOrNull { it.second } ?: sectionEnd
            val name = first
            val startIndex = lines.indexOf(scheduleLine)
            val before = lines.subList(1.coerceAtMost(lines.size), startIndex.coerceAtLeast(1)).filter { it.isNotBlank() }
            val after = if (startIndex + 1 <= lines.lastIndex) lines.subList(startIndex + 1, lines.size) else emptyList()
            val teacher = before.firstOrNull().orEmpty()
            val location = after.firstOrNull().orEmpty()
            onCourse(
                ParsedCourse(
                    name = name,
                    teacher = teacher,
                    location = location,
                    descriptor = lines.joinToString(" / "),
                    weekday = weekday,
                    weeks = weeks,
                    periods = periods,
                    startMinutes = start,
                    endMinutes = end,
                    raw = cellsJoin(lines)
                ),
                null
            )
        }
    }

    private fun cellsJoin(lines: List<String>): String = lines.joinToString(" | ")

    fun parseWeeks(text: String): List<Int> {
        // 只取「([周])」之前的周次部分，避免把后面的节次 [01-02节] 当成周次范围
        val base = text
            .substringBefore("([周])")
            .substringBefore("（[周]）")
            .substringBefore("([周]）")
            .substringBefore("（[周])")
        val cleaned = base.replace("（", "(").replace("）", ")")
        val weeks = sortedSetOf<Int>()
        for (token in cleaned.split(",", "，")) {
            val piece = token.trim()
            if (piece.isEmpty()) continue
            val parity = when {
                piece.contains("单") -> 1
                piece.contains("双") -> 0
                else -> -1
            }
            val range = Regex("""(\d+)\s*[-~—]\s*(\d+)""").find(piece)
            if (range != null) {
                val from = range.groupValues[1].toInt()
                val to = range.groupValues[2].toInt()
                for (week in from..to) {
                    if (parity == -1 || week % 2 == parity) weeks += week
                }
            } else {
                Regex("""\d+""").find(piece)?.let { match ->
                    val week = match.value.toInt()
                    if (parity == -1 || week % 2 == parity) weeks += week
                }
            }
        }
        return weeks.toList()
    }

    fun expandSessions(courses: List<ParsedCourse>, semesterStart: LocalDate): List<ParsedSession> {
        val monday = semesterStart.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        val sessions = mutableListOf<ParsedSession>()
        for (course in courses) {
            for (week in course.weeks) {
                val day = monday.plusWeeks((week - 1).toLong()).plusDays(course.weekday.toLong())
                sessions += ParsedSession(course, day, course.startMinutes, course.endMinutes)
            }
        }
        return sessions
    }
}
