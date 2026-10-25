package com.weeklyplanner.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.weeklyplanner.data.AccountEntity
import com.weeklyplanner.data.TransactionEntity
import com.weeklyplanner.domain.Categories
import com.weeklyplanner.domain.Category
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.domain.Money
import com.weeklyplanner.ui.components.CardSurface
import com.weeklyplanner.ui.components.ColorDot
import com.weeklyplanner.ui.components.EmptyState
import com.weeklyplanner.ui.components.SectionTitle
import java.time.LocalDate

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun FinanceScreen(
    categories: List<Category>,
    accounts: List<AccountEntity>,
    transactions: List<TransactionEntity>,
    balances: Map<Long, Long>,
    monthKey: String,
    onMonthChange: (String) -> Unit,
    onEditTransaction: (TransactionEntity) -> Unit,
    onDeleteTransaction: (Long) -> Unit
) {
    val accountNames = remember(accounts) { accounts.associate { it.id to it.name } }
    val monthTransactions = remember(transactions, monthKey) {
        transactions.filter { Dates.monthKey(Dates.toDate(it.occurredAt)) == monthKey }
    }
    val income = monthTransactions.filter { it.type == TransactionEntity.TYPE_INCOME }.sumOf { it.amountCents }
    val expense = monthTransactions.filter { it.type == TransactionEntity.TYPE_EXPENSE }.sumOf { it.amountCents }
    val totalBalance = balances.values.sum()
    val categoryTotals = monthTransactions
        .filter { it.type == TransactionEntity.TYPE_EXPENSE }
        .groupBy { it.categoryKey }
        .mapValues { entry -> entry.value.sumOf { it.amountCents } }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(top = 6.dp, bottom = 96.dp)
    ) {
        item {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = {
                    onMonthChange(Dates.monthKey(Dates.parseMonthKey(monthKey).minusMonths(1)))
                }) { Icon(Icons.Filled.ChevronLeft, contentDescription = "上个月") }
                Text(
                    Dates.monthLabel(monthKey),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                )
                IconButton(onClick = {
                    onMonthChange(Dates.monthKey(Dates.parseMonthKey(monthKey).plusMonths(1)))
                }) { Icon(Icons.Filled.ChevronRight, contentDescription = "下个月") }
            }
        }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                Text("总余额", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(4.dp))
                Text(
                    Money.format(totalBalance),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text("本月支出", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            Money.format(expense),
                            style = MaterialTheme.typography.titleSmall,
                            color = MaterialTheme.colorScheme.error,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            softWrap = false,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    Column(Modifier.weight(1f)) {
                        Text("本月收入", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            Money.format(income),
                            style = MaterialTheme.typography.titleSmall,
                            color = Color(0xFF2E7D32),
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            softWrap = false,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    Column(Modifier.weight(1f)) {
                        Text("本月结余", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            Money.format(income - expense),
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            softWrap = false,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    "总余额 = 各资金分区初始余额 + 收入 − 支出",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (accounts.isEmpty()) {
                    Text(
                        "还没有资金分区：去「我的 → 资金分区」添加并设置初始余额",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }
        }
        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                Text("支出分类", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(10.dp))
                categories.forEach { category ->
                    val amount = categoryTotals[category.key] ?: 0L
                    val ratio = if (expense > 0) (amount.toFloat() / expense.toFloat()) else 0f
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 4.dp)) {
                        ColorDot(Color(category.argb))
                        Spacer(Modifier.width(8.dp))
                        Text(category.label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.width(44.dp))
                        LinearProgressIndicator(
                            progress = { ratio },
                            modifier = Modifier
                                .weight(1f)
                                .height(6.dp)
                                .clip(RoundedCornerShape(3.dp)),
                            color = Color(category.argb),
                            trackColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            Money.format(amount),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                val knownKeys = categories.map { it.key }.toSet()
                val otherTotal = categoryTotals.filterKeys { it !in knownKeys }.values.sum()
                if (otherTotal > 0) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 4.dp)) {
                        ColorDot(Color(0xFF90A4AE))
                        Spacer(Modifier.width(8.dp))
                        Text("其他", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.width(44.dp))
                        Spacer(Modifier.weight(1f))
                        Text(
                            Money.format(otherTotal),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }
        item { SectionTitle("本月明细") }
        if (monthTransactions.isEmpty()) {
            item { EmptyState("本月还没有账目", "点右下角「记一笔」开始记账") }
        } else {
            items(monthTransactions, key = { it.id }) { transaction ->
                val category = Categories.category(transaction.categoryKey, categories)
                val color = if (transaction.type == TransactionEntity.TYPE_INCOME) Color(0xFF2E7D32) else Color(0xFFC0392B)
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 3.dp)
                        .clip(RoundedCornerShape(14.dp)),
                    color = MaterialTheme.colorScheme.surface,
                    onClick = { onEditTransaction(transaction) }
                ) {
                    Row(
                        Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        ColorDot(if (transaction.type == TransactionEntity.TYPE_INCOME) Color(0xFF2E7D32) else Color(category.argb), 12)
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                transaction.title.ifBlank { Categories.label(transaction.categoryKey, categories) },
                                style = MaterialTheme.typography.bodyLarge,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text(
                                listOfNotNull(
                                    accountNames[transaction.accountId],
                                    Dates.dayLabel(Dates.toDate(transaction.occurredAt))
                                ).joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Text(
                            if (transaction.type == TransactionEntity.TYPE_INCOME) "+" + Money.format(transaction.amountCents)
                            else "-" + Money.format(transaction.amountCents),
                            color = color,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                }
            }
        }
    }
}
