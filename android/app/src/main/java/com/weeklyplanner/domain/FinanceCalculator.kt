package com.weeklyplanner.domain

import com.weeklyplanner.data.TransactionEntity

data class MonthFigures(
    val month: String,
    val incomeCents: Long,
    val expenseCents: Long,
    val openingCents: Long,
    val closingCents: Long,
    val categories: Map<String, Long>
) {
    val netCents: Long get() = incomeCents - expenseCents
}

object FinanceCalculator {
    /** 某月报表：期初 = 所有账户初始余额 + 此前所有收入 - 此前所有支出；期末 = 期初 + 本月收入 - 本月支出。 */
    fun monthFigures(
        month: String,
        openingBalanceCents: Long,
        incomeBeforeCents: Long,
        expenseBeforeCents: Long,
        monthTransactions: List<TransactionEntity>
    ): MonthFigures {
        var income = 0L
        var expense = 0L
        val categories = mutableMapOf<String, Long>()
        for (tx in monthTransactions) {
            if (tx.type == TransactionEntity.TYPE_INCOME) {
                income += tx.amountCents
            } else {
                expense += tx.amountCents
                categories[tx.categoryKey] = (categories[tx.categoryKey] ?: 0L) + tx.amountCents
            }
        }
        val opening = openingBalanceCents + incomeBeforeCents - expenseBeforeCents
        return MonthFigures(
            month = month,
            incomeCents = income,
            expenseCents = expense,
            openingCents = opening,
            closingCents = opening + income - expense,
            categories = categories
        )
    }

    /** 账户余额 = 初始 + 收入 - 支出 - 转出 + 转入。 */
    fun accountBalance(
        openingCents: Long,
        incomeCents: Long,
        expenseCents: Long,
        transfersOutCents: Long,
        transfersInCents: Long
    ): Long = openingCents + incomeCents - expenseCents - transfersOutCents + transfersInCents

    fun sum(transactions: List<TransactionEntity>, type: String): Long =
        transactions.filter { it.type == type }.sumOf { it.amountCents }
}
