package com.weeklyplanner.backup

import androidx.room.withTransaction
import com.weeklyplanner.WeeklyApp
import com.weeklyplanner.data.AccountEntity
import com.weeklyplanner.data.CourseEntity
import com.weeklyplanner.data.CourseSessionEntity
import com.weeklyplanner.data.MonthlyReportEntity
import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.SettingEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.data.TransactionEntity
import com.weeklyplanner.data.TransferEntity
import org.json.JSONArray
import org.json.JSONObject

/**
 * 与 Windows 版互通的数据格式。
 *
 * 根节点：format = "weekly-planner-exchange"，version = 1，source = "android" | "windows"。
 * 金额一律用「分」；时间一律用 epoch 毫秒（UTC）。
 */
object BackupManager {
    const val FORMAT = "weekly-planner-exchange"
    const val VERSION = 1

    /** 安卓界面用中文优先级，互通文件用 normal/important/urgent。 */
    private fun priorityOut(label: String): String = when (label) {
        "重要" -> "important"
        "紧急" -> "urgent"
        else -> "normal"
    }

    private fun priorityIn(value: String): String = when (value) {
        "important", "重要" -> "重要"
        "urgent", "紧急" -> "紧急"
        else -> "普通"
    }

    suspend fun exportJson(app: WeeklyApp): String {
        val dao = app.database.backupDao()
        val root = JSONObject()
        root.put("format", FORMAT)
        root.put("version", VERSION)
        root.put("source", "android")
        root.put("app", "weekly-planner-android")
        root.put("exportedAt", System.currentTimeMillis())

        root.put("tasks", JSONArray().apply {
            dao.tasks().forEach { task ->
                put(JSONObject().apply {
                    put("id", task.id)
                    put("title", task.title)
                    put("note", task.note)
                    put("kind", task.kind)
                    put("priority", priorityOut(task.priority))
                    if (task.dueAt == null) put("dueAt", JSONObject.NULL) else put("dueAt", task.dueAt)
                    put("done", task.done)
                    put("createdAt", task.createdAt)
                    put("updatedAt", task.updatedAt)
                })
            }
        })
        root.put("plans", JSONArray().apply {
            dao.plans().forEach { plan ->
                put(JSONObject().apply {
                    put("id", plan.id)
                    put("taskId", plan.taskId)
                    put("planAt", plan.planAt)
                })
            }
        })
        root.put("accounts", JSONArray().apply {
            dao.accounts().forEach { account ->
                put(JSONObject().apply {
                    put("id", account.id)
                    put("name", account.name)
                    put("openingCents", account.openingCents)
                    put("sortOrder", account.sortOrder)
                    put("archived", account.archived)
                    put("createdAt", account.createdAt)
                })
            }
        })
        root.put("transactions", JSONArray().apply {
            dao.transactions().forEach { tx ->
                put(JSONObject().apply {
                    put("id", tx.id)
                    put("type", tx.type)
                    put("amountCents", tx.amountCents)
                    put("categoryKey", tx.categoryKey)
                    put("accountId", tx.accountId)
                    put("title", tx.title)
                    put("note", tx.note)
                    put("occurredAt", tx.occurredAt)
                    put("createdAt", tx.createdAt)
                })
            }
        })
        root.put("transfers", JSONArray().apply {
            dao.transfers().forEach { transfer ->
                put(JSONObject().apply {
                    put("id", transfer.id)
                    put("fromAccountId", transfer.fromAccountId)
                    put("toAccountId", transfer.toAccountId)
                    put("amountCents", transfer.amountCents)
                    put("note", transfer.note)
                    put("occurredAt", transfer.occurredAt)
                    put("createdAt", transfer.createdAt)
                })
            }
        })
        root.put("reports", JSONArray().apply {
            dao.reports().forEach { report ->
                put(JSONObject().apply {
                    put("month", report.month)
                    put("incomeCents", report.incomeCents)
                    put("expenseCents", report.expenseCents)
                    put("openingCents", report.openingCents)
                    put("closingCents", report.closingCents)
                    put("categoryJson", report.categoryJson)
                    put("createdAt", report.createdAt)
                })
            }
        })
        root.put("settings", JSONArray().apply {
            dao.settings().forEach { setting ->
                put(JSONObject().apply {
                    put("key", setting.key)
                    put("value", setting.value)
                })
            }
        })
        root.put("courses", JSONArray().apply {
            dao.courses().forEach { course ->
                put(JSONObject().apply {
                    put("id", course.id)
                    put("name", course.name)
                    put("teacher", course.teacher)
                    put("location", course.location)
                    put("descriptor", course.descriptor)
                    put("color", course.color)
                    put("createdAt", course.createdAt)
                })
            }
        })
        root.put("courseSessions", JSONArray().apply {
            dao.courseSessions().forEach { session ->
                put(JSONObject().apply {
                    put("id", session.id)
                    put("courseId", session.courseId)
                    put("day", session.day)
                    put("startMinutes", session.startMinutes)
                    put("endMinutes", session.endMinutes)
                })
            }
        })
        return root.toString(2)
    }

    suspend fun importJson(app: WeeklyApp, text: String): Map<String, Int> {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) throw IllegalArgumentException("文件是空的。")
        val root = try {
            JSONObject(trimmed)
        } catch (e: Exception) {
            throw IllegalArgumentException("这不是有效的 JSON 文件：${e.message}")
        }
        val isExchange = root.optString("format") == FORMAT
        val isAndroidOld = root.optString("app") == "weekly-planner-android"
        if (!isExchange && !isAndroidOld) {
            throw IllegalArgumentException(
                "不是一周日程的互通 JSON（缺少 format 字段）。\n" +
                    "请确认选择的是 Windows「导出 JSON」或安卓「导出备份」生成的文件。"
            )
        }

        val tasks = root.optJSONArray("tasks")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                TaskEntity(
                    id = item.getLong("id"),
                    title = item.getString("title"),
                    note = item.optString("note"),
                    kind = item.optString("kind", "学习"),
                    priority = priorityIn(item.optString("priority", "normal")),
                    dueAt = if (item.isNull("dueAt")) null else item.getLong("dueAt"),
                    done = item.optBoolean("done"),
                    createdAt = item.optLong("createdAt", System.currentTimeMillis()),
                    updatedAt = item.optLong("updatedAt", System.currentTimeMillis())
                )
            }
        }.orEmpty()

        val plans = root.optJSONArray("plans")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                PlanTimeEntity(
                    id = item.getLong("id"),
                    taskId = item.getLong("taskId"),
                    planAt = item.getLong("planAt")
                )
            }
        }.orEmpty()

        val accounts = root.optJSONArray("accounts")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                AccountEntity(
                    id = item.getLong("id"),
                    name = item.getString("name"),
                    openingCents = item.optLong("openingCents"),
                    sortOrder = item.optInt("sortOrder"),
                    archived = item.optBoolean("archived"),
                    createdAt = item.optLong("createdAt", System.currentTimeMillis())
                )
            }
        }.orEmpty()

        val transactions = root.optJSONArray("transactions")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                TransactionEntity(
                    id = item.getLong("id"),
                    type = item.getString("type"),
                    amountCents = item.getLong("amountCents"),
                    categoryKey = item.optString("categoryKey"),
                    accountId = item.getLong("accountId"),
                    title = item.optString("title"),
                    note = item.optString("note"),
                    occurredAt = item.getLong("occurredAt"),
                    createdAt = item.optLong("createdAt", System.currentTimeMillis())
                )
            }
        }.orEmpty()

        val transfers = root.optJSONArray("transfers")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                TransferEntity(
                    id = item.getLong("id"),
                    fromAccountId = item.getLong("fromAccountId"),
                    toAccountId = item.getLong("toAccountId"),
                    amountCents = item.getLong("amountCents"),
                    note = item.optString("note"),
                    occurredAt = item.getLong("occurredAt"),
                    createdAt = item.optLong("createdAt", System.currentTimeMillis())
                )
            }
        }.orEmpty()

        val reports = root.optJSONArray("reports")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                MonthlyReportEntity(
                    month = item.getString("month"),
                    incomeCents = item.getLong("incomeCents"),
                    expenseCents = item.getLong("expenseCents"),
                    openingCents = item.getLong("openingCents"),
                    closingCents = item.getLong("closingCents"),
                    categoryJson = item.optString("categoryJson", "{}"),
                    createdAt = item.optLong("createdAt", System.currentTimeMillis())
                )
            }
        }.orEmpty()

        val settings = root.optJSONArray("settings")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                SettingEntity(item.getString("key"), item.getString("value"))
            }
        }.orEmpty()

        val courses = root.optJSONArray("courses")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                CourseEntity(
                    id = item.getLong("id"),
                    name = item.getString("name"),
                    teacher = item.optString("teacher"),
                    location = item.optString("location"),
                    descriptor = item.optString("descriptor"),
                    color = item.optString("color", "#6C8AE4"),
                    createdAt = item.optLong("createdAt", System.currentTimeMillis())
                )
            }
        }.orEmpty()

        val courseSessions = root.optJSONArray("courseSessions")?.let { array ->
            (0 until array.length()).map { i ->
                val item = array.getJSONObject(i)
                CourseSessionEntity(
                    id = item.getLong("id"),
                    courseId = item.getLong("courseId"),
                    day = item.getString("day"),
                    startMinutes = item.getInt("startMinutes"),
                    endMinutes = item.getInt("endMinutes")
                )
            }
        }.orEmpty()

        app.database.withTransaction {
            val dao = app.database.backupDao()
            val hasAccounts = root.has("accounts")
            dao.clearReminders()
            dao.clearPlans()
            dao.clearTasks()
            dao.clearTransactions()
            dao.clearTransfers()
            // 旧备份可能没有 accounts 字段；此时保留本机资金分区，避免把总资产清空
            if (hasAccounts) dao.clearAccounts()
            dao.clearReports()
            // 设置（提醒时间、主题、日程视图、自定义分类）不属于互通数据，导入时保留本机设置
            dao.clearCourseSessions()
            dao.clearCourses()
            if (accounts.isNotEmpty()) dao.insertAccounts(accounts)
            if (tasks.isNotEmpty()) dao.insertTasks(tasks)
            if (plans.isNotEmpty()) dao.insertPlans(plans)
            if (transactions.isNotEmpty()) dao.insertTransactions(transactions)
            if (transfers.isNotEmpty()) dao.insertTransfers(transfers)
            if (reports.isNotEmpty()) dao.insertReports(reports)
            if (settings.isNotEmpty()) dao.insertSettings(settings)
            if (courses.isNotEmpty()) dao.insertCourses(courses)
            if (courseSessions.isNotEmpty()) dao.insertCourseSessions(courseSessions)
        }
        app.scheduleRepository.refreshReminders()
        return mapOf(
            "tasks" to tasks.size,
            "accounts" to accounts.size,
            "transactions" to transactions.size,
            "courses" to courses.size,
            "courseSessions" to courseSessions.size
        )
    }
}
