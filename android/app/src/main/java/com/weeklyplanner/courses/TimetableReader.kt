package com.weeklyplanner.courses

import java.io.ByteArrayInputStream
import java.io.File
import java.util.zip.ZipFile
import org.xmlpull.v1.XmlPullParser
import org.xmlpull.v1.XmlPullParserFactory

/** 读取 .xls / .xlsx / .csv 课表文件，统一成二维字符串表格。 */
object TimetableReader {
    fun readRows(fileName: String, bytes: ByteArray): List<List<String>> {
        val name = fileName.lowercase()
        return when {
            name.endsWith(".csv") || name.endsWith(".txt") -> readCsv(bytes)
            name.endsWith(".xlsx") -> readXlsx(bytes)
            name.endsWith(".xls") -> readXls(bytes)
            else -> throw ParseError("只支持 .xls / .xlsx / .csv 文件。")
        }
    }

    fun readCsv(bytes: ByteArray): List<List<String>> {
        val text = decode(bytes)
        val delimiter = detectDelimiter(text)
        val rows = parseDelimited(text, delimiter)
        return rows.map { row -> row.map { it.trim() } }.filter { row -> row.any { it.isNotEmpty() } }
    }

    private fun decode(bytes: ByteArray): String {
        val withoutBom = if (bytes.size >= 3 && bytes[0] == 0xEF.toByte() && bytes[1] == 0xBB.toByte() && bytes[2] == 0xBF.toByte()) {
            bytes.copyOfRange(3, bytes.size)
        } else {
            bytes
        }
        return try {
            withoutBom.toString(Charsets.UTF_8)
        } catch (e: Exception) {
            try {
                withoutBom.toString(charset("GB18030"))
            } catch (e2: Exception) {
                withoutBom.toString(Charsets.ISO_8859_1)
            }
        }
    }

    private fun detectDelimiter(text: String): Char {
        val sample = text.lineSequence().take(8).joinToString("\n")
        val counts = mapOf(',' to sample.count { it == ',' }, '\t' to sample.count { it == '\t' }, ';' to sample.count { it == ';' })
        return counts.maxByOrNull { it.value }?.takeIf { it.value > 0 }?.key ?: ','
    }

    private fun parseDelimited(text: String, delimiter: Char): List<List<String>> {
        val rows = mutableListOf<List<String>>()
        val field = StringBuilder()
        var row = mutableListOf<String>()
        var inQuotes = false
        var index = 0
        while (index < text.length) {
            val ch = text[index]
            when {
                inQuotes && ch == '"' && index + 1 < text.length && text[index + 1] == '"' -> {
                    field.append('"')
                    index++
                }
                ch == '"' -> inQuotes = !inQuotes
                ch == delimiter && !inQuotes -> {
                    row.add(field.toString())
                    field.clear()
                }
                (ch == '\n' || ch == '\r') && !inQuotes -> {
                    if (ch == '\r' && index + 1 < text.length && text[index + 1] == '\n') index++
                    row.add(field.toString())
                    field.clear()
                    if (row.any { it.isNotBlank() }) rows.add(row)
                    row = mutableListOf()
                }
                else -> field.append(ch)
            }
            index++
        }
        if (field.isNotEmpty() || row.isNotEmpty()) {
            row.add(field.toString())
            if (row.any { it.isNotBlank() }) rows.add(row)
        }
        return rows
    }

    fun readXls(bytes: ByteArray): List<List<String>> {
        return try {
            val workbook = jxl.Workbook.getWorkbook(ByteArrayInputStream(bytes))
            try {
                val sheet = workbook.sheets[0]
                // jxl 会把合并单元格的内容复制到整个区域；这里只保留左上角，
                // 和 Excel/Python 读取行为一致，避免「军训」被复制到周一~周日。
                val covered = mutableSetOf<Pair<Int, Int>>()
                runCatching {
                    sheet.mergedCells.forEach { range ->
                        val topLeft = range.topLeft
                        val bottomRight = range.bottomRight
                        for (row in topLeft.row..bottomRight.row) {
                            for (column in topLeft.column..bottomRight.column) {
                                if (row != topLeft.row || column != topLeft.column) {
                                    covered += column to row
                                }
                            }
                        }
                    }
                }
                (0 until sheet.rows).map { row ->
                    (0 until sheet.columns).map { column ->
                        if ((column to row) in covered) {
                            ""
                        } else {
                            sheet.getCell(column, row).contents.orEmpty()
                        }
                    }
                }
            } finally {
                workbook.close()
            }
        } catch (e: Exception) {
            throw ParseError("读取 .xls 失败：${e.message ?: "文件可能已损坏"}")
        }
    }

    fun readXlsx(bytes: ByteArray): List<List<String>> {
        val temp = File.createTempFile("timetable", ".xlsx")
        return try {
            temp.writeBytes(bytes)
            ZipFile(temp).use { zip ->
                val shared = parseSharedStrings(zip)
                val sheets = zip.entries().asSequence()
                    .filter { it.name.matches(Regex("""xl/worksheets/sheet\d+\.xml""")) }
                    .sortedBy { it.name }
                    .toList()
                if (sheets.isEmpty()) throw ParseError("找不到工作表。")
                var firstRows: List<List<String>>? = null
                for (entry in sheets) {
                    val rows = parseSheetXml(zip, entry, shared)
                    if (rows.isEmpty()) continue
                    if (firstRows == null) firstRows = rows
                    if (looksLikeFlatSheet(rows)) return rows
                }
                firstRows ?: throw ParseError("表格是空的。")
            }
        } catch (e: ParseError) {
            throw e
        } catch (e: Exception) {
            throw ParseError("读取 .xlsx 失败：${e.message ?: "文件可能已损坏"}")
        } finally {
            temp.delete()
        }
    }

    private fun looksLikeFlatSheet(rows: List<List<String>>): Boolean =
        rows.take(10).any { row ->
            row.any { it.contains("课程名称") || it.trim() == "课程" } &&
                row.any { it.contains("星期") }
        }

    private fun parseSheetXml(
        zip: ZipFile,
        sheetEntry: java.util.zip.ZipEntry,
        shared: List<String>
    ): List<List<String>> {
        val rows = sortedMapOf<Int, MutableMap<Int, String>>()
        var maxColumn = 0
        zip.getInputStream(sheetEntry).use { input ->
            val parser = XmlPullParserFactory.newInstance().newPullParser()
            parser.setInput(input, "UTF-8")
            var rowIndex = -1
            var columnIndex = -1
            var cellType = ""
            var inValue = false
            var inInlineText = false
            var value = StringBuilder()
            var event = parser.eventType
            while (event != XmlPullParser.END_DOCUMENT) {
                when (event) {
                    XmlPullParser.START_TAG -> when (parser.name) {
                        "row" -> {
                            rowIndex = parser.getAttributeValue(null, "r")?.toIntOrNull()?.minus(1) ?: (rowIndex + 1)
                        }
                        "c" -> {
                            val ref = parser.getAttributeValue(null, "r").orEmpty()
                            columnIndex = columnFromRef(ref)
                            cellType = parser.getAttributeValue(null, "t").orEmpty()
                            value = StringBuilder()
                        }
                        "v" -> inValue = true
                        "t" -> inInlineText = true
                    }
                    XmlPullParser.TEXT -> {
                        if (inValue || inInlineText) value.append(parser.text)
                    }
                    XmlPullParser.END_TAG -> when (parser.name) {
                        "v" -> inValue = false
                        "t" -> inInlineText = false
                        "c" -> {
                            val text = when {
                                cellType == "s" -> shared.getOrNull(value.toString().toIntOrNull() ?: -1).orEmpty()
                                else -> value.toString()
                            }
                            if (rowIndex >= 0 && columnIndex >= 0 && text.isNotBlank()) {
                                rows.getOrPut(rowIndex) { mutableMapOf() }[columnIndex] = text
                                maxColumn = maxOf(maxColumn, columnIndex)
                            }
                        }
                    }
                }
                event = parser.next()
            }
        }
        if (rows.isEmpty()) return emptyList()
        val lastRow = rows.lastKey()
        return (0..lastRow).map { row ->
            val cells = rows[row] ?: emptyMap()
            (0..maxColumn).map { column -> cells[column] ?: "" }
        }
    }

    private fun parseSharedStrings(zip: ZipFile): List<String> {
        val entry = zip.getEntry("xl/sharedStrings.xml") ?: return emptyList()
        val result = mutableListOf<String>()
        zip.getInputStream(entry).use { input ->
            val parser = XmlPullParserFactory.newInstance().newPullParser()
            parser.setInput(input, "UTF-8")
            var inText = false
            var current = StringBuilder()
            var event = parser.eventType
            while (event != XmlPullParser.END_DOCUMENT) {
                when (event) {
                    XmlPullParser.START_TAG -> when (parser.name) {
                        "si" -> current = StringBuilder()
                        "t" -> inText = true
                    }
                    XmlPullParser.TEXT -> if (inText) current.append(parser.text)
                    XmlPullParser.END_TAG -> when (parser.name) {
                        "t" -> inText = false
                        "si" -> result += current.toString()
                    }
                }
                event = parser.next()
            }
        }
        return result
    }

    private fun columnFromRef(ref: String): Int {
        var value = 0
        for (ch in ref) {
            if (ch.isLetter()) {
                value = value * 26 + (ch.uppercaseChar() - 'A' + 1)
            } else {
                break
            }
        }
        return value - 1
    }
}
