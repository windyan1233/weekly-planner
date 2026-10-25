package com.weeklyplanner.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        TaskEntity::class,
        PlanTimeEntity::class,
        ReminderEntity::class,
        AccountEntity::class,
        TransactionEntity::class,
        TransferEntity::class,
        MonthlyReportEntity::class,
        SettingEntity::class,
        CourseEntity::class,
        CourseSessionEntity::class
    ],
    version = 2,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun taskDao(): TaskDao
    abstract fun reminderDao(): ReminderDao
    abstract fun financeDao(): FinanceDao
    abstract fun settingsDao(): SettingsDao
    abstract fun backupDao(): BackupDao
    abstract fun courseDao(): CourseDao

    companion object {
        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `courses` (" +
                        "`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, " +
                        "`name` TEXT NOT NULL, `teacher` TEXT NOT NULL, `location` TEXT NOT NULL, " +
                        "`descriptor` TEXT NOT NULL, `color` TEXT NOT NULL, `createdAt` INTEGER NOT NULL)"
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_courses_name` ON `courses` (`name`)")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `course_sessions` (" +
                        "`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, `courseId` INTEGER NOT NULL, " +
                        "`day` TEXT NOT NULL, `startMinutes` INTEGER NOT NULL, `endMinutes` INTEGER NOT NULL, " +
                        "FOREIGN KEY(`courseId`) REFERENCES `courses`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE)"
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_course_sessions_courseId` ON `course_sessions` (`courseId`)")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_course_sessions_day` ON `course_sessions` (`day`)")
            }
        }

        @Volatile
        private var instance: AppDatabase? = null

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "planner.db"
                ).addMigrations(MIGRATION_1_2).build().also { instance = it }
            }
    }
}
