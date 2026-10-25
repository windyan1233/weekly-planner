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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.weeklyplanner.data.MonthlyReportEntity
import com.weeklyplanner.domain.Categories
import com.weeklyplanner.domain.Category
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.domain.Money
import com.weeklyplanner.domain.MonthFigures
import com.weeklyplanner.ui.components.CardSurface
import com.weeklyplanner.ui.components.EmptyState
import com.weeklyplanner.ui.components.SectionTitle

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun ReportScreen(
    categories: List<Category>,
    report: MonthFigures?,
    reports: List<MonthlyReportEntity>,
    monthKey: String,
    onMonthChange: (String) -> Unit,
    onSaveSnapshot: () -> Unit
) {
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
                    textAlign = TextAlign.Center
                )
                IconButton(onClick = {
                    onMonthChange(Dates.monthKey(Dates.parseMonthKey(monthKey).plusMonths(1)))
                }) { Icon(Icons.Filled.ChevronRight, contentDescription = "下个月") }
            }
        }

        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                Text("本月概览", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    Column {
                        Text("收入", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            Money.format(report?.incomeCents ?: 0L),
                            style = MaterialTheme.typography.titleMedium,
                            color = Color(0xFF2E7D32),
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                    Column {
                        Text("支出", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            Money.format(report?.expenseCents ?: 0L),
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.error,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                    Column {
                        Text("结余", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            Money.format(report?.netCents ?: 0L),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    Column {
                        Text("期初余额", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(Money.format(report?.openingCents ?: 0L), style = MaterialTheme.typography.bodyMedium)
                    }
                    Column {
                        Text("期末余额", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(Money.format(report?.closingCents ?: 0L), style = MaterialTheme.typography.bodyMedium)
                    }
                }
                Spacer(Modifier.height(6.dp))
                TextButton(onClick = onSaveSnapshot) { Text("保存本月报表快照") }
            }
        }

        item {
            CardSurface(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                Text("支出分类", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                val total = report?.expenseCents ?: 0L
                categories.forEach { category ->
                    val amount = report?.categories?.get(category.key) ?: 0L
                    val ratio = if (total > 0) amount.toFloat() / total.toFloat() else 0f
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 4.dp)) {
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
                        Spacer(Modifier.padding(horizontal = 4.dp))
                        Text(Money.format(amount), style = MaterialTheme.typography.bodySmall)
                    }
                }
                val knownKeys = categories.map { it.key }.toSet()
                val other = report?.categories?.filterKeys { it !in knownKeys }?.values?.sum() ?: 0L
                if (other > 0) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 4.dp)) {
                        Text("其他", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.width(44.dp))
                        Spacer(Modifier.weight(1f))
                        Text(Money.format(other), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }

        item { SectionTitle("历史月报") }
        if (reports.isEmpty()) {
            item { EmptyState("还没有历史报表", "查看月报后会自动生成快照") }
        } else {
            items(reports, key = { it.month }) { item ->
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 3.dp)
                        .clip(RoundedCornerShape(14.dp)),
                    color = MaterialTheme.colorScheme.surface,
                    onClick = { onMonthChange(item.month) }
                ) {
                    Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(Dates.monthLabel(item.month), style = MaterialTheme.typography.bodyLarge)
                            Text(
                                "收入 ${Money.format(item.incomeCents)} · 支出 ${Money.format(item.expenseCents)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Text(
                            Money.format(item.closingCents),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                }
            }
        }
    }
}
