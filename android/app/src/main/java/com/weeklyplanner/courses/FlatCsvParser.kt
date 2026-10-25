package com.weeklyplanner.courses

/** 扁平 CSV（一行一门课）解析，以及课表格式判断。 */
object FlatCsvParser {
    private val aliases = mapOf(
        "name" to listOf("课程", "课程名称", "科目", "名称"),
        "weekday" to listOf("星期", "周几", "星期几"),
        "periods" to listOf("节次", "小节", "节"),
        "weeks" to listOf("周次", "周数"),
        "time" to listOf("时间", "上课时间"),
        "location" to listOf("地点", "教室", "上课地点", "场地"),
        "teacher" to listOf("教师", "老师")
    )

    fun isGrid(rows: List<List<String>>): Boolean =
        rows.take(10).any { row -> TimetableParser.weekdayNames.count { name -> row.any { it.contains(name) } } >= 5 }

    fun parse(rows: List<List<String>>): ParseResult {
        var hasTimetableTimes = false
        if (rows.isEmpty()) throw ParseError("文件是空的。")
        val headerIndex = rows.take(10).indexOfFirst { row ->
            findColumn(row, "name") != null && findColumn(row, "weekday") != null
        }
        if (headerIndex < 0) throw ParseError("没有找到「课程、星期」这样的表头，无法按 CSV 识别。")
        val header = rows[headerIndex]
        val columns = aliases.keys.associateWith { findColumn(header, it) }
        val courses = mutableListOf<ParsedCourse>()
        val seen = mutableSetOf<String>()
        val warnings = mutableListOf<String>()
        for (row in rows.drop(headerIndex + 1)) {
            if (row.all { it.isBlank() }) continue
            fun value(key: String): String {
                val index = columns[key] ?: return ""
                return row.getOrNull(index)?.trim().orEmpty()
            }
            val name = value("name").trimEnd('●', '◆', '★', '☆', '■', '□')
            if (name.isBlank()) continue
            val weekday = parseWeekday(value("weekday"))
            if (weekday == null) {
                warnings += "跳过（星期无法识别）：$name"
                continue
            }
            val weeks = TimetableParser.parseWeeks(value("weeks"))
            if (weeks.isEmpty()) {
                warnings += "跳过（周次无法识别）：$name"
                continue
            }
            val periods = Regex("""\d+""").findAll(value("periods")).map { it.value.toInt() }.toList()
            if (periods.isEmpty()) {
                warnings += "跳过（节次无法识别）：$name"
                continue
            }
            val mappedTimes = periods.mapNotNull { TimetableParser.defaultPeriodTimes[it] }
            val defaultTimes = if (mappedTimes.isEmpty()) {
                null
            } else {
                mappedTimes.minOf { it.first } to mappedTimes.maxOf { it.second }
            }
            val explicitTimes = parseTimeRange(value("time"))
            if (explicitTimes != null) hasTimetableTimes = true
            val times = explicitTimes ?: defaultTimes
            if (times == null) {
                warnings += "跳过（缺少时间）：$name"
                continue
            }
            val key = listOf(name, value("teacher"), value("location"), weekday, weeks, periods).joinToString("|")
            if (!seen.add(key)) continue
            courses += ParsedCourse(
                name = name,
                teacher = value("teacher"),
                location = value("location"),
                descriptor = row.joinToString(" | ") { it },
                weekday = weekday,
                weeks = weeks,
                periods = periods,
                startMinutes = times.first,
                endMinutes = times.second,
                raw = row.joinToString(" | ") { it }
            )
        }
        if (courses.isEmpty()) throw ParseError("CSV 里没有解析出任何课程。")
        return ParseResult(
            courses.sortedWith(compareBy({ it.weekday }, { it.startMinutes }, { it.name })),
            warnings,
            hasTimetableTimes = hasTimetableTimes
        )
    }

    private fun findColumn(row: List<String>, key: String): Int? {
        val names = aliases[key] ?: return null
        return row.indexOfFirst { cell -> names.any { cell.replace(Regex("""[\s*＊:：()（）]"""), "").contains(it) } }
    }

    private fun parseWeekday(text: String): Int? {
        TimetableParser.weekdayNames.forEachIndexed { index, name -> if (text.contains(name)) return index }
        listOf("周一", "周二", "周三", "周四", "周五", "周六", "周日").forEachIndexed { index, name ->
            if (text.contains(name)) return index
        }
        Regex("""[1-7]""").find(text)?.let { return it.value.toInt() - 1 }
        return null
    }

    private fun parseTimeRange(text: String): Pair<Int, Int>? {
        val match = Regex("""(\d{1,2})[:：](\d{2})\s*[-~—]\s*(\d{1,2})[:：](\d{2})""").find(text) ?: return null
        val start = match.groupValues[1].toInt() * 60 + match.groupValues[2].toInt()
        val end = match.groupValues[3].toInt() * 60 + match.groupValues[4].toInt()
        return if (end > start) start to end else null
    }
}
