package com.weeklyplanner.domain

import com.weeklyplanner.data.PlanTimeEntity
import com.weeklyplanner.data.TaskEntity
import com.weeklyplanner.data.TransactionEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

class MoneyTest {
    @Test
    fun parses_basic_amounts() {
        assertEquals(1250L, Money.parseToCents("12.5"))
        assertEquals(1200L, Money.parseToCents("12"))
        assertEquals(5L, Money.parseToCents("0.05"))
        assertEquals(100000L, Money.parseToCents("1,000"))
        assertEquals(1234L, Money.parseToCents("12.34"))
    }

    @Test
    fun rejects_invalid_amounts() {
        assertNull(Money.parseToCents(""))
        assertNull(Money.parseToCents("abc"))
        assertNull(Money.parseToCents("1.234"))
        assertNull(Money.parseToCents("-1"))
        assertNull(Money.parseToCents("1e3"))
    }

    @Test
    fun formats_money() {
        assertEquals("¥0.00", Money.format(0))
        assertEquals("¥12.34", Money.format(1234))
        assertEquals("¥1,234.56", Money.format(123456))
        assertEquals("-¥12.34", Money.formatSigned(-1234))
    }
}

class DatesTest {
    @Test
    fun week_starts_on_monday() {
        val sunday = LocalDate.of(2026, 9, 27)
        assertEquals(LocalDate.of(2026, 9, 21), Dates.startOfWeek(sunday))
        assertEquals(LocalDate.of(2026, 9, 21), Dates.startOfWeek(LocalDate.of(2026, 9, 21)))
        assertEquals(7, Dates.weekDays(LocalDate.of(2026, 9, 21)).size)
    }

    @Test
    fun month_helpers() {
        assertEquals("2026-09", Dates.monthKey(LocalDate.of(2026, 9, 15)))
        assertEquals(LocalDate.of(2026, 10, 1), Dates.endOfMonthExclusive(LocalDate.of(2026, 9, 15)))
        assertEquals("2026 年 9 月", Dates.monthLabel("2026-09"))
    }

    @Test
    fun weekday_label() {
        assertEquals("周一", Dates.weekdayLabel(LocalDate.of(2026, 9, 21)))
        assertEquals("周日", Dates.weekdayLabel(LocalDate.of(2026, 9, 27)))
    }
}

class ReminderPlannerTest {
    private val zone = ZoneId.systemDefault()

    private fun at(date: LocalDate, hour: Int, minute: Int): Long =
        date.atTime(LocalTime.of(hour, minute)).atZone(zone).toInstant().toEpochMilli()

    private val settings = AppSettings(reminderHour = 9, reminderMinute = 0, planLeadMinutes = 10)

    private fun task(dueAt: Long? = null, remindDue: Boolean = true): TaskEntity =
        TaskEntity(id = 1L, title = "任务", dueAt = dueAt, remindDue = remindDue)

    private fun plan(
        id: Long = 7L,
        startAt: Long,
        endAt: Long? = null,
        remindStart: Boolean = true,
        remindEnd: Boolean = false
    ): PlanTimeEntity = PlanTimeEntity(
        id = id,
        taskId = 1L,
        planAt = startAt,
        endAt = endAt,
        remindStart = remindStart,
        remindEnd = remindEnd
    )

    @Test
    fun due_reminder_is_day_before_at_nine() {
        val due = at(LocalDate.of(2026, 9, 22), 18, 0)
        val fire = ReminderPlanner.dueFireAt(due, 9, 0)
        assertEquals(at(LocalDate.of(2026, 9, 21), 9, 0), fire)
    }

    @Test
    fun due_reminder_respects_custom_time() {
        val due = at(LocalDate.of(2026, 10, 1), 8, 0)
        val fire = ReminderPlanner.dueFireAt(due, 20, 30)
        assertEquals(at(LocalDate.of(2026, 9, 30), 20, 30), fire)
    }

    @Test
    fun plan_reminder_lead_time() {
        val planAt = at(LocalDate.of(2026, 9, 21), 10, 0)
        assertEquals(planAt - 10 * 60_000L, ReminderPlanner.planFireAt(planAt, 10))
        assertEquals(planAt, ReminderPlanner.planFireAt(planAt, 0))
    }

    @Test
    fun specs_include_due_and_plans() {
        val due = at(LocalDate.of(2026, 9, 25), 12, 0)
        val start = at(LocalDate.of(2026, 9, 23), 9, 0)
        val specs = ReminderPlanner.specs(
            tasks = listOf(task(dueAt = due)),
            plans = mapOf(1L to listOf(plan(startAt = start))),
            settings = settings
        )
        assertEquals(2, specs.size)
        assertEquals("due", specs[0].kind)
        assertEquals("plan", specs[1].kind)
        assertEquals(7L, specs[1].planKey)
    }

    // ------------------------------------------------------------ 三个开关

    @Test
    fun due_switch_off_skips_due_reminder() {
        val due = at(LocalDate.of(2026, 9, 25), 12, 0)
        val specs = ReminderPlanner.specs(
            tasks = listOf(task(dueAt = due, remindDue = false)),
            plans = emptyMap(),
            settings = settings
        )
        assertTrue(specs.isEmpty())
    }

    @Test
    fun start_switch_off_skips_plan_reminder() {
        val start = at(LocalDate.of(2026, 9, 23), 9, 0)
        val specs = ReminderPlanner.specs(
            tasks = listOf(task()),
            plans = mapOf(1L to listOf(plan(startAt = start, remindStart = false))),
            settings = settings
        )
        assertTrue(specs.isEmpty())
    }

    @Test
    fun end_reminder_fires_exactly_at_end_time() {
        val start = at(LocalDate.of(2026, 9, 23), 22, 0)
        val end = at(LocalDate.of(2026, 9, 24), 1, 30)
        val specs = ReminderPlanner.specs(
            tasks = listOf(task()),
            plans = mapOf(
                1L to listOf(plan(startAt = start, endAt = end, remindStart = false, remindEnd = true))
            ),
            settings = settings
        )
        assertEquals(1, specs.size)
        assertEquals("plan_end", specs[0].kind)
        assertEquals(7L, specs[0].planKey)
        // 结束提醒不提前，就是结束时间本身
        assertEquals(end, specs[0].fireAt)
        assertEquals(end, specs[0].anchorAt)
    }

    @Test
    fun end_reminder_needs_end_time() {
        val start = at(LocalDate.of(2026, 9, 23), 9, 0)
        val specs = ReminderPlanner.specs(
            tasks = listOf(task()),
            plans = mapOf(1L to listOf(plan(startAt = start, endAt = null, remindEnd = true))),
            settings = settings
        )
        // 没有结束时间时，即使「提醒结束」开着也不会生成结束提醒，只剩开始提醒
        assertEquals(listOf("plan"), specs.map { it.kind })
    }

    @Test
    fun end_reminder_is_off_by_default() {
        val start = at(LocalDate.of(2026, 9, 23), 9, 0)
        val end = at(LocalDate.of(2026, 9, 23), 11, 0)
        val specs = ReminderPlanner.specs(
            tasks = listOf(task()),
            plans = mapOf(1L to listOf(plan(startAt = start, endAt = end))),
            settings = settings
        )
        assertEquals(listOf("plan"), specs.map { it.kind })
    }

    @Test
    fun all_three_switches_on_produce_three_specs() {
        val due = at(LocalDate.of(2026, 9, 25), 12, 0)
        val start = at(LocalDate.of(2026, 9, 23), 22, 0)
        val end = at(LocalDate.of(2026, 9, 24), 9, 30)
        val specs = ReminderPlanner.specs(
            tasks = listOf(task(dueAt = due, remindDue = true)),
            plans = mapOf(
                1L to listOf(plan(startAt = start, endAt = end, remindStart = true, remindEnd = true))
            ),
            settings = settings
        )
        assertEquals(listOf("due", "plan", "plan_end"), specs.map { it.kind })
        assertEquals(ReminderPlanner.planFireAt(start, 10), specs[1].fireAt)
        assertEquals(end, specs[2].fireAt)
    }
}

class FinanceCalculatorTest {
    private fun tx(id: Long, type: String, cents: Long, category: String, at: Long): TransactionEntity =
        TransactionEntity(
            id = id,
            type = type,
            amountCents = cents,
            categoryKey = category,
            accountId = 1L,
            occurredAt = at
        )

    @Test
    fun account_balance_formula() {
        val balance = FinanceCalculator.accountBalance(
            openingCents = 10000,
            incomeCents = 5000,
            expenseCents = 2000,
            transfersOutCents = 1000,
            transfersInCents = 500
        )
        assertEquals(12500L, balance)
    }

    @Test
    fun month_report_carries_opening_balance() {
        val transactions = listOf(
            tx(1, TransactionEntity.TYPE_INCOME, 50000, "", 0),
            tx(2, TransactionEntity.TYPE_EXPENSE, 3000, "food", 0),
            tx(3, TransactionEntity.TYPE_EXPENSE, 2000, "life", 0)
        )
        val figures = FinanceCalculator.monthFigures(
            month = "2026-09",
            openingBalanceCents = 10000,
            incomeBeforeCents = 50000,
            expenseBeforeCents = 5000,
            monthTransactions = transactions.takeLast(2)
        )
        assertEquals(55000L, figures.openingCents)
        assertEquals(0L, figures.incomeCents)
        assertEquals(5000L, figures.expenseCents)
        assertEquals(50000L, figures.closingCents)
        assertEquals(3000L, figures.categories["food"])
        assertEquals(2000L, figures.categories["life"])
    }

    @Test
    fun empty_month_keeps_balance() {
        val figures = FinanceCalculator.monthFigures(
            month = "2026-10",
            openingBalanceCents = 10000,
            incomeBeforeCents = 0,
            expenseBeforeCents = 0,
            monthTransactions = emptyList()
        )
        assertEquals(10000L, figures.openingCents)
        assertEquals(10000L, figures.closingCents)
        assertEquals(0L, figures.netCents)
    }
}
