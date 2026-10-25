package com.weeklyplanner.data

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
abstract class TaskDao {
    @Query("SELECT * FROM tasks ORDER BY done ASC, dueAt ASC, id DESC")
    abstract fun observeAll(): Flow<List<TaskEntity>>

    @Query("SELECT * FROM plan_times ORDER BY planAt")
    abstract fun observeAllPlans(): Flow<List<PlanTimeEntity>>

    @Query("SELECT * FROM plan_times WHERE planAt >= :start AND planAt < :end ORDER BY planAt")
    abstract fun observePlansBetween(start: Long, end: Long): Flow<List<PlanTimeEntity>>

    @Query("SELECT * FROM tasks WHERE id = :id")
    abstract suspend fun get(id: Long): TaskEntity?

    @Query("SELECT * FROM tasks")
    abstract suspend fun all(): List<TaskEntity>

    @Query("SELECT * FROM plan_times WHERE taskId = :taskId ORDER BY planAt")
    abstract suspend fun plansFor(taskId: Long): List<PlanTimeEntity>

    @Query("SELECT * FROM plan_times")
    abstract suspend fun allPlans(): List<PlanTimeEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insert(task: TaskEntity): Long

    @Update
    abstract suspend fun update(task: TaskEntity)

    @Query("DELETE FROM tasks WHERE id = :id")
    abstract suspend fun delete(id: Long)

    @Insert
    abstract suspend fun insertPlans(plans: List<PlanTimeEntity>)

    @Query("DELETE FROM plan_times WHERE taskId = :taskId")
    abstract suspend fun deletePlans(taskId: Long)

    @Transaction
    open suspend fun saveTask(task: TaskEntity, plans: List<PlanTimeEntity>): Long {
        val id = if (task.id == 0L) insert(task) else {
            update(task)
            task.id
        }
        deletePlans(id)
        if (plans.isNotEmpty()) {
            insertPlans(plans.map { it.copy(taskId = id) })
        }
        return id
    }

    @Transaction
    open suspend fun deleteTask(id: Long) {
        delete(id)
    }

    @Transaction
    open suspend fun setDone(id: Long, done: Boolean) {
        val task = get(id) ?: return
        update(task.copy(done = done, updatedAt = System.currentTimeMillis()))
    }
}

@Dao
abstract class ReminderDao {
    @Query("SELECT * FROM reminders WHERE status = 'pending' ORDER BY fireAt")
    abstract suspend fun pending(): List<ReminderEntity>

    @Query("SELECT * FROM reminders WHERE status = 'pending' ORDER BY fireAt")
    abstract fun observePending(): Flow<List<ReminderEntity>>

    @Query("SELECT * FROM reminders WHERE taskId = :taskId")
    abstract suspend fun forTask(taskId: Long): List<ReminderEntity>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun insert(reminder: ReminderEntity): Long

    @Query("UPDATE reminders SET status = :status WHERE id = :id")
    abstract suspend fun setStatus(id: Long, status: String)

    @Query("DELETE FROM reminders WHERE taskId = :taskId")
    abstract suspend fun deleteForTask(taskId: Long)

    @Query("DELETE FROM reminders WHERE id = :id")
    abstract suspend fun delete(id: Long)

    @Query("DELETE FROM reminders")
    abstract suspend fun clear()

    @Query("SELECT * FROM reminders WHERE id = :id")
    abstract suspend fun get(id: Long): ReminderEntity?

    @Query("SELECT * FROM reminders")
    abstract suspend fun all(): List<ReminderEntity>

    @Query("SELECT * FROM reminders WHERE status = 'pending' AND fireAt <= :now ORDER BY fireAt")
    abstract suspend fun due(now: Long): List<ReminderEntity>

    @Query("UPDATE reminders SET snoozeCount = snoozeCount + 1")
    abstract suspend fun bumpSnooze()
}

@Dao
abstract class FinanceDao {
    @Query("SELECT * FROM accounts ORDER BY sortOrder, id")
    abstract fun observeAccounts(): Flow<List<AccountEntity>>

    @Query("SELECT * FROM accounts ORDER BY sortOrder, id")
    abstract suspend fun accounts(): List<AccountEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAccount(account: AccountEntity): Long

    @Update
    abstract suspend fun updateAccount(account: AccountEntity)

    @Query("SELECT COALESCE(SUM(amountCents), 0) FROM transactions WHERE accountId = :accountId AND type = 'income'")
    abstract suspend fun incomeFor(accountId: Long): Long

    @Query("SELECT COALESCE(SUM(amountCents), 0) FROM transactions WHERE accountId = :accountId AND type = 'expense'")
    abstract suspend fun expenseFor(accountId: Long): Long

    @Query("SELECT COALESCE(SUM(amountCents), 0) FROM transfers WHERE fromAccountId = :accountId")
    abstract suspend fun transfersOut(accountId: Long): Long

    @Query("SELECT COALESCE(SUM(amountCents), 0) FROM transfers WHERE toAccountId = :accountId")
    abstract suspend fun transfersIn(accountId: Long): Long

    @Query("SELECT * FROM transactions WHERE occurredAt >= :start AND occurredAt < :end ORDER BY occurredAt DESC, id DESC")
    abstract fun observeTransactions(start: Long, end: Long): Flow<List<TransactionEntity>>

    @Query("SELECT * FROM transactions ORDER BY occurredAt DESC, id DESC")
    abstract fun observeAllTransactions(): Flow<List<TransactionEntity>>

    @Query("SELECT * FROM transactions WHERE occurredAt >= :start AND occurredAt < :end ORDER BY occurredAt DESC, id DESC")
    abstract suspend fun transactionsBetween(start: Long, end: Long): List<TransactionEntity>

    @Query("SELECT * FROM transactions ORDER BY occurredAt")
    abstract suspend fun allTransactions(): List<TransactionEntity>

    @Insert
    abstract suspend fun insertTransaction(transaction: TransactionEntity): Long

    @Update
    abstract suspend fun updateTransaction(transaction: TransactionEntity)

    @Query("DELETE FROM transactions WHERE id = :id")
    abstract suspend fun deleteTransaction(id: Long)

    @Query("SELECT * FROM transfers WHERE occurredAt >= :start AND occurredAt < :end ORDER BY occurredAt DESC, id DESC")
    abstract fun observeTransfers(start: Long, end: Long): Flow<List<TransferEntity>>

    @Query("SELECT * FROM transfers ORDER BY occurredAt DESC, id DESC")
    abstract fun observeAllTransfers(): Flow<List<TransferEntity>>

    @Query("SELECT * FROM transfers ORDER BY occurredAt")
    abstract suspend fun allTransfers(): List<TransferEntity>

    @Insert
    abstract suspend fun insertTransfer(transfer: TransferEntity): Long

    @Query("DELETE FROM transfers WHERE id = :id")
    abstract suspend fun deleteTransfer(id: Long)

    @Query("SELECT * FROM monthly_reports ORDER BY month DESC")
    abstract fun observeReports(): Flow<List<MonthlyReportEntity>>

    @Query("SELECT * FROM monthly_reports WHERE month = :month")
    abstract suspend fun report(month: String): MonthlyReportEntity?

    @Query("SELECT * FROM monthly_reports ORDER BY month DESC")
    abstract suspend fun allReports(): List<MonthlyReportEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun saveReport(report: MonthlyReportEntity)

    @Query("SELECT COALESCE(SUM(amountCents), 0) FROM transactions WHERE type = 'income' AND occurredAt < :before")
    abstract suspend fun incomeBefore(before: Long): Long

    @Query("SELECT COALESCE(SUM(amountCents), 0) FROM transactions WHERE type = 'expense' AND occurredAt < :before")
    abstract suspend fun expenseBefore(before: Long): Long
}

@Dao
abstract class SettingsDao {
    @Query("SELECT value FROM settings WHERE key = :key")
    abstract suspend fun get(key: String): String?

    @Query("SELECT * FROM settings")
    abstract fun observeAll(): Flow<List<SettingEntity>>

    @Query("SELECT * FROM settings")
    abstract suspend fun allRows(): List<SettingEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun set(setting: SettingEntity)

    @Query("DELETE FROM settings WHERE key = :key")
    abstract suspend fun delete(key: String)
}
