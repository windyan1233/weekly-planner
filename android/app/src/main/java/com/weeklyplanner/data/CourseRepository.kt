package com.weeklyplanner.data

import com.weeklyplanner.courses.ParsedCourse
import com.weeklyplanner.courses.ParseResult
import com.weeklyplanner.courses.TimetableParser
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.flow.Flow

class CourseRepository(private val db: AppDatabase) {
    private val dao = db.courseDao()
    private val colors = listOf(
        "#6C8AE4", "#D79A38", "#57AE84", "#C97F6B",
        "#9B87E8", "#5FA8A0", "#DD7BA6", "#8C8FE0"
    )

    val courses: Flow<List<CourseEntity>> = dao.observeCourses()

    suspend fun sessionsBetween(start: LocalDate, end: LocalDate): List<CourseSessionEntity> =
        dao.sessionsBetween(start.toString(), end.toString())

    suspend fun stats(): Pair<Int, Int> = dao.courseCount() to dao.sessionCount()

    suspend fun import(result: ParseResult, semesterStart: LocalDate): Pair<Int, Int> {
        val groups = linkedMapOf<String, MutableList<ParsedCourse>>()
        for (course in result.courses) {
            val key = listOf(course.name, course.teacher, course.location, course.descriptor).joinToString("|")
            groups.getOrPut(key) { mutableListOf() } += course
        }
        val courseEntities = mutableListOf<CourseEntity>()
        val sessions = mutableListOf<CourseSessionEntity>()
        groups.entries.forEachIndexed { index, (key, items) ->
            val first = items.first()
            val courseId = index + 1L
            courseEntities += CourseEntity(
                id = courseId,
                name = first.name,
                teacher = first.teacher,
                location = first.location,
                descriptor = first.descriptor,
                color = colors[index % colors.size]
            )
            val expanded = TimetableParser.expandSessions(items, semesterStart)
            expanded.forEach { session ->
                sessions += CourseSessionEntity(
                    courseId = courseId,
                    day = session.day.toString(),
                    startMinutes = session.startMinutes,
                    endMinutes = session.endMinutes
                )
            }
        }
        dao.replaceAll(courseEntities, sessions)
        return dao.courseCount() to dao.sessionCount()
    }

    suspend fun clear() = dao.clearAll()
}
