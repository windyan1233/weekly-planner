package com.weeklyplanner.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

/** 课程：从教务系统课表导入，不参与任务与提醒。 */
@Entity(tableName = "courses", indices = [Index("name")])
data class CourseEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val name: String,
    val teacher: String = "",
    val location: String = "",
    val descriptor: String = "",
    val color: String = "#6C8AE4",
    val createdAt: Long = System.currentTimeMillis()
)

/** 每次课：具体日期 + 起止分钟。 */
@Entity(
    tableName = "course_sessions",
    foreignKeys = [
        ForeignKey(
            entity = CourseEntity::class,
            parentColumns = ["id"],
            childColumns = ["courseId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("courseId"), Index("day")]
)
data class CourseSessionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val courseId: Long,
    /** ISO 日期，例如 2026-09-21 */
    val day: String,
    val startMinutes: Int,
    val endMinutes: Int
)

@Dao
abstract class CourseDao {
    @Query("SELECT * FROM courses ORDER BY name")
    abstract fun observeCourses(): Flow<List<CourseEntity>>

    @Query("SELECT * FROM courses ORDER BY name")
    abstract suspend fun courses(): List<CourseEntity>

    @Query("SELECT COUNT(*) FROM courses")
    abstract suspend fun courseCount(): Int

    @Query("SELECT COUNT(*) FROM course_sessions")
    abstract suspend fun sessionCount(): Int

    @Query("SELECT * FROM course_sessions")
    abstract suspend fun sessions(): List<CourseSessionEntity>

    @Query("SELECT * FROM course_sessions WHERE day >= :start AND day <= :end ORDER BY day, startMinutes")
    abstract suspend fun sessionsBetween(start: String, end: String): List<CourseSessionEntity>

    @Insert
    abstract suspend fun insertCourse(course: CourseEntity): Long

    @Insert
    abstract suspend fun insertSessions(items: List<CourseSessionEntity>)

    @Query("DELETE FROM course_sessions")
    abstract suspend fun clearSessions()

    @Query("DELETE FROM courses")
    abstract suspend fun clearCourses()

    @Transaction
    open suspend fun replaceAll(courses: List<CourseEntity>, sessions: List<CourseSessionEntity>) {
        clearSessions()
        clearCourses()
        for (course in courses) {
            val id = insertCourse(course.copy(id = 0L))
            val rows = sessions.filter { it.courseId == course.id }
                .map { it.copy(id = 0L, courseId = id) }
            if (rows.isNotEmpty()) insertSessions(rows)
        }
    }

    @Transaction
    open suspend fun clearAll() {
        clearSessions()
        clearCourses()
    }
}
