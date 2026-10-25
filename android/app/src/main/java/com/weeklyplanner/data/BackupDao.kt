package com.weeklyplanner.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface BackupDao {
    @Query("DELETE FROM reminders")
    suspend fun clearReminders()

    @Query("DELETE FROM plan_times")
    suspend fun clearPlans()

    @Query("DELETE FROM tasks")
    suspend fun clearTasks()

    @Query("DELETE FROM transactions")
    suspend fun clearTransactions()

    @Query("DELETE FROM transfers")
    suspend fun clearTransfers()

    @Query("DELETE FROM accounts")
    suspend fun clearAccounts()

    @Query("DELETE FROM monthly_reports")
    suspend fun clearReports()

    @Query("DELETE FROM settings")
    suspend fun clearSettings()

    @Query("DELETE FROM course_sessions")
    suspend fun clearCourseSessions()

    @Query("DELETE FROM courses")
    suspend fun clearCourses()

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTasks(items: List<TaskEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPlans(items: List<PlanTimeEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAccounts(items: List<AccountEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTransactions(items: List<TransactionEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTransfers(items: List<TransferEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertReports(items: List<MonthlyReportEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertSettings(items: List<SettingEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertCourses(items: List<CourseEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertCourseSessions(items: List<CourseSessionEntity>)

    @Query("SELECT * FROM tasks")
    suspend fun tasks(): List<TaskEntity>

    @Query("SELECT * FROM plan_times")
    suspend fun plans(): List<PlanTimeEntity>

    @Query("SELECT * FROM accounts")
    suspend fun accounts(): List<AccountEntity>

    @Query("SELECT * FROM transactions")
    suspend fun transactions(): List<TransactionEntity>

    @Query("SELECT * FROM transfers")
    suspend fun transfers(): List<TransferEntity>

    @Query("SELECT * FROM monthly_reports")
    suspend fun reports(): List<MonthlyReportEntity>

    @Query("SELECT * FROM settings")
    suspend fun settings(): List<SettingEntity>

    @Query("SELECT * FROM courses")
    suspend fun courses(): List<CourseEntity>

    @Query("SELECT * FROM course_sessions")
    suspend fun courseSessions(): List<CourseSessionEntity>
}
