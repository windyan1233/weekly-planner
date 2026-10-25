package com.weeklyplanner.data

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

/** 任务：标题、备注、分类、优先级、截止时间，可以挂多个计划时间。 */
@Entity(
    tableName = "tasks",
    indices = [Index("dueAt"), Index("done")]
)
data class TaskEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val title: String,
    val note: String = "",
    val kind: String = "学习",
    val priority: String = "普通",
    val dueAt: Long? = null,
    val done: Boolean = false,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis()
)

/** 计划时间：一个任务可以有多个，互相独立。 */
@Entity(
    tableName = "plan_times",
    foreignKeys = [
        ForeignKey(
            entity = TaskEntity::class,
            parentColumns = ["id"],
            childColumns = ["taskId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("taskId"), Index("planAt")]
)
data class PlanTimeEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val taskId: Long,
    val planAt: Long
)

/** 提醒：每条任务最多一条截止提醒 + 每个计划时间一条。 */
@Entity(
    tableName = "reminders",
    indices = [
        Index(value = ["taskId", "kind", "planKey", "anchorAt"], unique = true),
        Index("fireAt"),
        Index("status")
    ]
)
data class ReminderEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val taskId: Long,
    /** due = 截止前一天；plan = 计划时间前 */
    val kind: String,
    /** 计划时间 id；截止提醒为 0 */
    val planKey: Long = 0L,
    val fireAt: Long,
    /** 计算提醒时依据的截止/计划时间，用于去重 */
    val anchorAt: Long,
    val status: String = STATUS_PENDING,
    val snoozeCount: Int = 0,
    val createdAt: Long = System.currentTimeMillis()
) {
    companion object {
        const val STATUS_PENDING = "pending"
        const val STATUS_SENT = "sent"
        const val STATUS_MISSED = "missed"
        const val KIND_DUE = "due"
        const val KIND_PLAN = "plan"
    }
}

/** 资金分区（账户）。 */
@Entity(tableName = "accounts", indices = [Index("sortOrder")])
data class AccountEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val name: String,
    /** 初始余额（分） */
    val openingCents: Long = 0L,
    val sortOrder: Int = 0,
    val archived: Boolean = false,
    val createdAt: Long = System.currentTimeMillis()
)

/** 收入 / 支出。 */
@Entity(
    tableName = "transactions",
    foreignKeys = [
        ForeignKey(
            entity = AccountEntity::class,
            parentColumns = ["id"],
            childColumns = ["accountId"],
            onDelete = ForeignKey.RESTRICT
        )
    ],
    indices = [Index("occurredAt"), Index("accountId"), Index("categoryKey")]
)
data class TransactionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val type: String,
    val amountCents: Long,
    /** 支出分类 key；收入为空 */
    val categoryKey: String = "",
    val accountId: Long,
    val title: String = "",
    val note: String = "",
    val occurredAt: Long,
    val createdAt: Long = System.currentTimeMillis()
) {
    companion object {
        const val TYPE_EXPENSE = "expense"
        const val TYPE_INCOME = "income"
    }
}

/** 资金分区之间的转账。 */
@Entity(
    tableName = "transfers",
    foreignKeys = [
        ForeignKey(
            entity = AccountEntity::class,
            parentColumns = ["id"],
            childColumns = ["fromAccountId"],
            onDelete = ForeignKey.RESTRICT
        ),
        ForeignKey(
            entity = AccountEntity::class,
            parentColumns = ["id"],
            childColumns = ["toAccountId"],
            onDelete = ForeignKey.RESTRICT
        )
    ],
    indices = [Index("occurredAt"), Index("fromAccountId"), Index("toAccountId")]
)
data class TransferEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val fromAccountId: Long,
    val toAccountId: Long,
    val amountCents: Long,
    val note: String = "",
    val occurredAt: Long,
    val createdAt: Long = System.currentTimeMillis()
)

/** 月度报表快照（月末结转用）。 */
@Entity(tableName = "monthly_reports")
data class MonthlyReportEntity(
    @PrimaryKey val month: String,
    val incomeCents: Long,
    val expenseCents: Long,
    val openingCents: Long,
    val closingCents: Long,
    /** JSON: {"food":1234,...} */
    val categoryJson: String,
    val createdAt: Long = System.currentTimeMillis()
)

/** 设置项。 */
@Entity(tableName = "settings")
data class SettingEntity(
    @PrimaryKey val key: String,
    val value: String
)
