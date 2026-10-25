package com.weeklyplanner.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.weeklyplanner.data.AccountEntity
import com.weeklyplanner.data.TransactionEntity
import com.weeklyplanner.domain.Categories
import com.weeklyplanner.domain.Category
import com.weeklyplanner.domain.Dates
import com.weeklyplanner.domain.Money
import com.weeklyplanner.ui.components.DatePickerModal
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun QuickAddSheet(
    categories: List<Category>,
    accounts: List<AccountEntity>,
    editing: TransactionEntity?,
    initialType: String,
    onDismiss: () -> Unit,
    onSave: (String, Long, String, Long, String, String, Long) -> Unit,
    onUpdate: (TransactionEntity) -> Unit,
    onTransfer: (Long, Long, Long, String, Long) -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var type by remember(editing) {
        mutableStateOf(
            when (editing?.type) {
                TransactionEntity.TYPE_INCOME -> "income"
                TransactionEntity.TYPE_EXPENSE -> "expense"
                else -> if (initialType == "transfer") "transfer" else "expense"
            }
        )
    }
    var amountText by remember(editing) {
        mutableStateOf(editing?.let { Money.formatPlain(it.amountCents) } ?: "")
    }
    var categoryKey by remember(editing, categories) {
        val existing = editing?.categoryKey?.takeIf { key ->
            key.isNotBlank() && categories.any { it.key == key }
        }
        mutableStateOf(existing ?: categories.firstOrNull()?.key ?: Categories.defaults.first().key)
    }
    var accountId by remember(editing, accounts) {
        mutableStateOf(editing?.accountId ?: accounts.firstOrNull()?.id ?: 0L)
    }
    var title by remember(editing) { mutableStateOf(editing?.title ?: "") }
    var note by remember(editing) { mutableStateOf(editing?.note ?: "") }
    var date by remember(editing) {
        mutableStateOf(editing?.let { Dates.toDate(it.occurredAt) } ?: Dates.today())
    }
    var fromAccountId by remember(accounts) { mutableStateOf(accounts.firstOrNull()?.id ?: 0L) }
    var toAccountId by remember(accounts) {
        mutableStateOf(accounts.getOrNull(1)?.id ?: accounts.firstOrNull()?.id ?: 0L)
    }
    var error by remember { mutableStateOf<String?>(null) }
    var showDate by remember { mutableStateOf(false) }

    val isEditing = editing != null

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 26.dp)
        ) {
            Text(
                if (isEditing) "编辑账目" else "记一笔",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(14.dp))
            if (!isEditing) {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf("支出", "收入", "转账").forEachIndexed { index, label ->
                        SegmentedButton(
                            selected = type == listOf("expense", "income", "transfer")[index],
                            onClick = { type = listOf("expense", "income", "transfer")[index] },
                            shape = SegmentedButtonDefaults.itemShape(index = index, count = 3)
                        ) { Text(label) }
                    }
                }
                Spacer(Modifier.height(14.dp))
            }

            OutlinedTextField(
                value = amountText,
                onValueChange = { amountText = it },
                label = { Text("金额") },
                prefix = { Text("¥") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth()
            )

            if (type == "transfer") {
                Spacer(Modifier.height(12.dp))
                AccountSelector("从", accounts, fromAccountId) { fromAccountId = it }
                Spacer(Modifier.height(8.dp))
                AccountSelector("到", accounts, toAccountId) { toAccountId = it }
            } else {
                Spacer(Modifier.height(12.dp))
                if (type == "expense") {
                    Text("分类", style = MaterialTheme.typography.labelLarge)
                    Spacer(Modifier.height(6.dp))
                    androidx.compose.foundation.layout.FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {                        categories.forEach { category ->
                            FilterChip(
                                selected = categoryKey == category.key,
                                onClick = { categoryKey = category.key },
                                label = { Text(category.label) }
                            )
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                }
                AccountSelector("资金分区", accounts, accountId) { accountId = it }
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("名称（选填）") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            }

            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = note,
                onValueChange = { note = it },
                label = { Text("备注（选填）") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(10.dp))
            OutlinedButton(onClick = { showDate = true }) {
                Text("日期：${date.monthValue} 月 ${date.dayOfMonth} 日")
            }

            if (error != null) {
                Spacer(Modifier.height(8.dp))
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }

            Spacer(Modifier.height(18.dp))
            Button(
                onClick = {
                    val cents = Money.parseToCents(amountText)
                    if (cents == null || cents <= 0) {
                        error = "请输入正确的金额，例如 12.5"
                        return@Button
                    }
                    val occurredAt = if (isEditing) {
                        editing!!.occurredAt
                    } else {
                        val nowTime = java.time.LocalTime.now()
                        Dates.atMillis(date, nowTime.hour, nowTime.minute)
                    }
                    when {
                        isEditing -> {
                            onUpdate(
                                editing!!.copy(
                                    amountCents = cents,
                                    categoryKey = if (editing.type == TransactionEntity.TYPE_EXPENSE) categoryKey else "",
                                    accountId = accountId,
                                    title = title.trim(),
                                    note = note.trim(),
                                    occurredAt = occurredAt
                                )
                            )
                        }
                        type == "transfer" -> {
                            if (fromAccountId == toAccountId) {
                                error = "转出和转入不能是同一个资金分区"
                                return@Button
                            }
                            onTransfer(fromAccountId, toAccountId, cents, note.trim(), occurredAt)
                        }
                        else -> {
                            onSave(
                                if (type == "income") TransactionEntity.TYPE_INCOME else TransactionEntity.TYPE_EXPENSE,
                                cents,
                                if (type == "expense") categoryKey else "",
                                accountId,
                                title.trim(),
                                note.trim(),
                                occurredAt
                            )
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text(if (isEditing) "保存修改" else "保存") }
        }
    }

    if (showDate) {
        DatePickerModal(date, onDismiss = { showDate = false }, onPick = { date = it })
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AccountSelector(
    label: String,
    accounts: List<AccountEntity>,
    selectedId: Long,
    onSelect: (Long) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedName = accounts.firstOrNull { it.id == selectedId }?.name ?: "选择资金分区"
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = selectedName,
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor()
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            accounts.forEach { account ->
                DropdownMenuItem(
                    text = { Text(account.name) },
                    onClick = {
                        onSelect(account.id)
                        expanded = false
                    }
                )
            }
        }
    }
}
