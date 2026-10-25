"""记账模块的对话框：初始化、记一笔、资金调动、资金分区、账户流水、分类明细、财务设置。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import finance_icons
from .finance_models import (
    CATEGORIES,
    CATEGORY_KEYS,
    CATEGORY_LABELS,
    CURRENCIES,
    EXPENSE,
    FinanceError,
    INCOME,
    MoneyError,
    format_money,
    month_display,
    parse_money,
)
from ..edition import editable_categories as is_editable_categories
from .finance_widgets import FlowRow


class FinanceDialog(QDialog):
    """统一外壳：标题 + 说明 + 内容 + 底部按钮。"""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        parent: QWidget | None = None,
        width: int = 520,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 18)
        outer.setSpacing(12)

        header = QVBoxLayout()
        header.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("Title")
        header.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("Muted")
            sub.setWordWrap(True)
            header.addWidget(sub)
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)
        outer.addStretch(1)

        self.error_label = QLabel("")
        self.error_label.setObjectName("ErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        outer.addWidget(self.error_label)

        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self._footer_stretch = False
        outer.addLayout(self.footer)

    # ------------------------------------------------------------------
    def _ensure_footer_stretch(self) -> None:
        if not self._footer_stretch:
            self.footer.addStretch(1)
            self._footer_stretch = True

    def field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        return label

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def add_cancel(self, text: str = "取消") -> QPushButton:
        self._ensure_footer_stretch()
        button = QPushButton(text)
        button.setObjectName("Ghost")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.reject)
        self.footer.addWidget(button)
        return button

    def add_primary(self, text: str) -> QPushButton:
        self._ensure_footer_stretch()
        button = QPushButton(text)
        button.setObjectName("Primary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setDefault(True)
        button.clicked.connect(self._on_primary)
        self.footer.addWidget(button)
        return button

    def _on_primary(self) -> None:  # 子类覆盖
        self.accept()

    def confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes


# --------------------------------------------------------------------------
# 金额输入
# --------------------------------------------------------------------------
class AmountEdit(QLineEdit):
    def __init__(self, symbol: str = "¥", decimals: int = 2, parent=None) -> None:
        super().__init__(parent)
        self.symbol = symbol
        self.decimals = decimals
        self.setPlaceholderText("0.00" if decimals else "0")
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setFixedWidth(150)

    def text_value(self) -> int:
        return parse_money(self.text(), self.decimals)

    def money_text(self) -> str:
        try:
            return format_money(self.text_value(), self.symbol, self.decimals)
        except MoneyError:
            return ""


class AmountRow(QWidget):
    def __init__(self, symbol: str, decimals: int, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.edit = AmountEdit(symbol, decimals)
        layout.addWidget(self.edit, 1)
        unit = QLabel(symbol)
        unit.setObjectName("Muted")
        layout.addWidget(unit)
        layout.addStretch(0)


def _date_edit(value: date | None = None) -> QDateEdit:
    widget = QDateEdit()
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("yyyy-MM-dd")
    widget.setDate(QDate(value.year, value.month, value.day) if value else QDate.currentDate())
    widget.setFixedWidth(130)
    return widget


def _to_date(widget: QDateEdit) -> date:
    value = widget.date()
    return date(value.year(), value.month(), value.day())


# --------------------------------------------------------------------------
# 初始化
# --------------------------------------------------------------------------
class InitialSetupDialog(FinanceDialog):
    def __init__(self, service, parent=None) -> None:
        super().__init__(
            "开始记账",
            "先输入现在手里的总金额，再把它分配到几个资金分区。分配金额合计不能超过总额，"
            "剩下的会自动放进「未分配资金」。",
            parent=parent,
            width=560,
        )
        self.service = service
        money = service.money

        total_row = QHBoxLayout()
        total_row.addWidget(self.field_label("现在的总金额"))
        total_row.addStretch(1)
        self.total_edit = AmountEdit(service.symbol, service.decimals)
        total_row.addWidget(self.total_edit)
        unit = QLabel(service.symbol)
        unit.setObjectName("Muted")
        total_row.addWidget(unit)
        self.body.addLayout(total_row)

        self.body.addSpacing(4)
        self.body.addWidget(self.field_label("资金分区"))
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(6)
        self.body.addLayout(self.rows_box)
        self._rows: list[tuple[QLineEdit, AmountEdit, QPushButton]] = []

        add_button = QPushButton("＋ 添加分区")
        add_button.setObjectName("Ghost")
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(lambda: self._add_row())
        self.body.addWidget(add_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)

        self.total_edit.textChanged.connect(self._update_summary)
        self._add_row("我的资金")
        self._update_summary()

        self.add_cancel()
        self.add_primary("开始记账")

    def _add_row(self, name: str = "") -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("分区名称，例如 日常生活费")
        layout.addWidget(name_edit, 1)
        amount = AmountEdit(self.service.symbol, self.service.decimals)
        amount.setPlaceholderText("0.00")
        amount.textChanged.connect(self._update_summary)
        layout.addWidget(amount)
        remove = QPushButton("×")
        remove.setObjectName("Ghost")
        remove.setFixedSize(30, 30)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda: self._remove_row(row))
        layout.addWidget(remove)
        self.rows_box.addWidget(row)
        self._rows.append((name_edit, amount, remove))
        name_edit.textChanged.connect(self._update_summary)

    def _remove_row(self, row: QWidget) -> None:
        for entry in list(self._rows):
            if entry[0].parent() is row:
                self._rows.remove(entry)
        row.setParent(None)
        row.deleteLater()
        self._update_summary()

    def _summary_values(self) -> tuple[int, int]:
        total = 0
        try:
            total = self.total_edit.text_value() if self.total_edit.text().strip() else 0
        except MoneyError:
            total = 0
        allocated = 0
        for name_edit, amount_edit, _button in self._rows:
            try:
                allocated += amount_edit.text_value() if amount_edit.text().strip() else 0
            except MoneyError:
                pass
        return total, allocated

    def _update_summary(self) -> None:
        total, allocated = self._summary_values()
        remainder = total - allocated
        money = self.service.money
        text = f"已分配 {money(allocated)}"
        if total > 0:
            text += f" / 总额 {money(total)} · 未分配 {money(max(remainder, 0))}"
        self.summary.setText(text)

    def _on_primary(self) -> None:
        try:
            total = self.total_edit.text_value()
        except MoneyError as exc:
            self.set_error(str(exc))
            return
        rows: list[tuple[str, int, str]] = []
        names: set[str] = set()
        for name_edit, amount_edit, _button in self._rows:
            name = name_edit.text().strip()
            if not name:
                self.set_error("请给每个资金分区起个名字。")
                return
            if name in names:
                self.set_error(f"资金分区「{name}」重复了。")
                return
            names.add(name)
            try:
                value = amount_edit.text_value() if amount_edit.text().strip() else 0
            except MoneyError as exc:
                self.set_error(f"「{name}」的金额不正确：{exc}")
                return
            rows.append((name, value, ""))
        if not rows:
            self.set_error("至少需要一个资金分区。")
            return
        allocated = sum(row[1] for row in rows)
        if allocated == 0 and len(rows) == 1:
            rows[0] = (rows[0][0], total, "")
            allocated = total
        if allocated > total:
            self.set_error(
                f"分配金额合计 {self.service.money(allocated)} 超过了总金额 "
                f"{self.service.money(total)}。"
            )
            return
        try:
            self.service.initialize(total, rows)
        except FinanceError as exc:
            self.set_error(str(exc))
            return
        self.accept()


# --------------------------------------------------------------------------
# 记一笔（收入 / 支出）
# --------------------------------------------------------------------------
class TransactionDialog(FinanceDialog):
    def __init__(self, service, *, kind: str = EXPENSE, transaction=None, parent=None) -> None:
        self.service = service
        self.transaction = transaction
        editing = transaction is not None
        title = "记一笔" if not editing else "修改账目"
        super().__init__(
            title,
            "金额会立即计入总余额与对应资金分区；支出会归入六个分类之一。",
            parent=parent,
            width=560,
        )
        self._kind = transaction.kind if editing else kind

        kind_row = QHBoxLayout()
        kind_row.addWidget(self.field_label("类型"))
        kind_row.addStretch(1)
        self.kind_box = QWidget()
        kind_layout = QHBoxLayout(self.kind_box)
        kind_layout.setContentsMargins(0, 0, 0, 0)
        kind_layout.setSpacing(6)
        self.kind_group = QButtonGroup(self)
        self.kind_group.setExclusive(True)
        self.income_button = QPushButton("收入")
        self.expense_button = QPushButton("支出")
        for button, value in ((self.income_button, INCOME), (self.expense_button, EXPENSE)):
            button.setObjectName("Segmented")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=value: self._set_kind(v))
            kind_layout.addWidget(button)
            self.kind_group.addButton(button)
        kind_row.addWidget(self.kind_box)
        self.body.addLayout(kind_row)
        self.income_button.setChecked(self._kind == INCOME)
        self.expense_button.setChecked(self._kind == EXPENSE)

        amount_row = QHBoxLayout()
        amount_row.addWidget(self.field_label("金额"))
        amount_row.addStretch(1)
        self.amount_edit = AmountEdit(service.symbol, service.decimals)
        amount_row.addWidget(self.amount_edit)
        unit = QLabel(service.symbol)
        unit.setObjectName("Muted")
        amount_row.addWidget(unit)
        self.body.addLayout(amount_row)

        date_row = QHBoxLayout()
        date_row.addWidget(self.field_label("日期"))
        date_row.addStretch(1)
        self.date_edit = _date_edit(transaction.occurred_on if editing else None)
        date_row.addWidget(self.date_edit)
        self.body.addLayout(date_row)

        title_row = QHBoxLayout()
        self.title_caption = self.field_label(
            ("来源（选填）" if self._kind == INCOME else "支出内容（选填）")
        )
        title_row.addWidget(self.title_caption)
        title_row.addStretch(1)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("选填，例如：生活费 / 午饭")
        self.title_edit.setFixedWidth(300)
        title_row.addWidget(self.title_edit)
        self.body.addLayout(title_row)

        self.category_label = self.field_label("支出分类")
        self.body.addWidget(self.category_label)
        self.category_box = QWidget()
        grid = QGridLayout(self.category_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)
        self.category_buttons: dict[str, QPushButton] = {}
        categories = service.categories.active()
        known = {item.key for item in categories}
        if (
            editing
            and transaction.kind == EXPENSE
            and transaction.category
            and transaction.category not in known
        ):
            try:
                categories.append(service.categories.get(transaction.category))
            except FinanceError:
                pass
        for index, category in enumerate(categories):
            button = QPushButton(category.label)
            button.setObjectName("CatChip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(finance_icons.category_icon(category.key, category.color, 16))
            button.setToolTip(service.categories.note(category.key))
            button.clicked.connect(lambda _=False, k=category.key: self._select_category(k))
            grid.addWidget(button, index // 3, index % 3)
            self.category_group.addButton(button)
            self.category_buttons[category.key] = button
        self.body.addWidget(self.category_box)

        account_row = QHBoxLayout()
        account_row.addWidget(self.field_label("资金分区"))
        account_row.addStretch(1)
        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(260)
        self.body.addLayout(account_row)
        account_row.addWidget(self.account_combo)

        note_row = QHBoxLayout()
        note_row.addWidget(self.field_label("备注"))
        note_row.addStretch(1)
        self.note_edit = QLineEdit()
        self.note_edit.setFixedWidth(300)
        self.note_edit.setPlaceholderText("选填")
        note_row.addWidget(self.note_edit)
        self.body.addLayout(note_row)

        # 数据填充
        balances = service.accounts.balances(include_archived=True)
        self._fill_accounts(balances, transaction.account_id if editing else None)
        if editing:
            self.amount_edit.setText(self._plain(transaction.amount_cents))
            self.title_edit.setText(transaction.title)
            self.note_edit.setText(transaction.note)
            if transaction.kind == EXPENSE:
                self._select_category(transaction.category)
        else:
            first_key = next(iter(self.category_buttons), "")
            if first_key:
                self._select_category(first_key)
        self._set_kind(self._kind)

        if editing:
            delete = QPushButton("删除")
            delete.setObjectName("DangerGhost")
            delete.setCursor(Qt.CursorShape.PointingHandCursor)
            delete.clicked.connect(self._delete)
            self.footer.addWidget(delete)
            self.footer.addStretch(1)
            self._footer_stretch = True
        self.add_cancel()
        self.add_primary("保存")
        self.amount_edit.setFocus()

    def _plain(self, cents: int) -> str:
        from .finance_models import format_money_plain

        return format_money_plain(cents, self.service.decimals)

    def _fill_accounts(self, balances, selected_id: int | None) -> None:
        self.account_combo.clear()
        for balance in balances:
            text = f"{balance.name} · {self.service.money(balance.balance_cents)}"
            if balance.account.archived:
                text += "（已归档）"
            self.account_combo.addItem(text, balance.account.id)
        if selected_id is not None:
            index = self.account_combo.findData(selected_id)
            if index >= 0:
                self.account_combo.setCurrentIndex(index)

    def _select_category(self, key: str) -> None:
        for value, button in self.category_buttons.items():
            button.setChecked(value == key)

    def _current_category(self) -> str:
        for key, button in self.category_buttons.items():
            if button.isChecked():
                return key
        return ""

    def _set_kind(self, kind: str) -> None:
        self._kind = kind
        self.income_button.setChecked(kind == INCOME)
        self.expense_button.setChecked(kind == EXPENSE)
        is_expense = kind == EXPENSE
        self.category_label.setVisible(is_expense)
        self.category_box.setVisible(is_expense)
        self.title_caption.setText(
            "来源（选填）" if not is_expense else "支出内容（选填）"
        )
        if not is_expense:
            for button in self.category_buttons.values():
                button.setChecked(False)
        elif not self._current_category() and self.category_buttons:
            next(iter(self.category_buttons.values())).setChecked(True)

    def _on_primary(self) -> None:
        try:
            amount = self.amount_edit.text_value()
        except MoneyError as exc:
            self.set_error(str(exc))
            return
        title = self.title_edit.text().strip()
        category = None
        if self._kind == EXPENSE:
            category = self._current_category()
            if not category:
                self.set_error("请选择支出分类。")
                return
        account_id = self.account_combo.currentData()
        if account_id is None:
            self.set_error("请先创建一个资金分区。")
            return
        note = self.note_edit.text().strip()
        day = _to_date(self.date_edit)
        try:
            if self.transaction is None:
                self.service.transactions.add(
                    self._kind, amount, day, title, category, int(account_id), note
                )
            else:
                self.service.transactions.update(
                    self.transaction.id,
                    kind=self._kind,
                    amount_cents=amount,
                    occurred_on=day,
                    title=title,
                    category=category,
                    account_id=int(account_id),
                    note=note,
                )
        except FinanceError as exc:
            self.set_error(str(exc))
            return
        self.service.after_change()
        self.accept()

    def _delete(self) -> None:
        if self.transaction is None:
            return
        if not self.confirm(
            "删除账目",
            f"确定删除「{self.transaction.title}」这笔记录吗？\n"
            "删除后余额与月报会立即重新计算。",
        ):
            return
        try:
            self.service.transactions.delete(self.transaction.id)
        except FinanceError as exc:
            self.set_error(str(exc))
            return
        self.service.after_change()
        self.accept()


# --------------------------------------------------------------------------
# 资金调动
# --------------------------------------------------------------------------
class TransferDialog(FinanceDialog):
    def __init__(self, service, parent=None) -> None:
        super().__init__(
            "资金调动",
            "把金额从一个分区转到另一个分区。转账不是收入也不是支出，总余额保持不变。",
            parent=parent,
            width=540,
        )
        self.service = service
        balances = service.accounts.balances(include_archived=False)
        if len(balances) < 2:
            self.set_error("至少需要两个资金分区才能调动资金。请先在「资金管理」里新增分区。")

        from_row = QHBoxLayout()
        from_row.addWidget(self.field_label("从"))
        from_row.addStretch(1)
        self.from_combo = QComboBox()
        self.from_combo.setMinimumWidth(250)
        from_row.addWidget(self.from_combo)
        self.body.addLayout(from_row)

        to_row = QHBoxLayout()
        to_row.addWidget(self.field_label("到"))
        to_row.addStretch(1)
        self.to_combo = QComboBox()
        self.to_combo.setMinimumWidth(250)
        to_row.addWidget(self.to_combo)
        self.body.addLayout(to_row)

        amount_row = QHBoxLayout()
        amount_row.addWidget(self.field_label("金额"))
        amount_row.addStretch(1)
        self.amount_edit = AmountEdit(service.symbol, service.decimals)
        amount_row.addWidget(self.amount_edit)
        unit = QLabel(service.symbol)
        unit.setObjectName("Muted")
        amount_row.addWidget(unit)
        self.body.addLayout(amount_row)

        date_row = QHBoxLayout()
        date_row.addWidget(self.field_label("日期"))
        date_row.addStretch(1)
        self.date_edit = _date_edit()
        date_row.addWidget(self.date_edit)
        self.body.addLayout(date_row)

        note_row = QHBoxLayout()
        note_row.addWidget(self.field_label("备注"))
        note_row.addStretch(1)
        self.note_edit = QLineEdit()
        self.note_edit.setFixedWidth(250)
        note_row.addWidget(self.note_edit)
        self.body.addLayout(note_row)

        self.balance_hint = QLabel("")
        self.balance_hint.setObjectName("Muted")
        self.body.addWidget(self.balance_hint)

        for balance in balances:
            text = f"{balance.name} · {service.money(balance.balance_cents)}"
            self.from_combo.addItem(text, balance.account.id)
            self.to_combo.addItem(text, balance.account.id)
        self.to_combo.setCurrentIndex(1 if len(balances) > 1 else 0)
        self.from_combo.currentIndexChanged.connect(self._update_hint)
        self.amount_edit.textChanged.connect(self._update_hint)
        self._update_hint()

        self.add_cancel()
        self.add_primary("确认调动")

    def _update_hint(self) -> None:
        account_id = self.from_combo.currentData()
        if account_id is None:
            return
        try:
            balance = self.service.accounts.balance(int(account_id))
        except FinanceError:
            return
        text = f"该分区当前余额 {self.service.money(balance)}"
        try:
            amount = self.amount_edit.text_value() if self.amount_edit.text().strip() else 0
        except MoneyError:
            amount = 0
        if amount:
            text += f" · 调动后剩 {self.service.money(balance - amount)}"
        self.balance_hint.setText(text)

    def _on_primary(self) -> None:
        from_id = self.from_combo.currentData()
        to_id = self.to_combo.currentData()
        if from_id is None or to_id is None:
            self.set_error("请选择分区。")
            return
        if from_id == to_id:
            self.set_error("转出和转入不能是同一个分区。")
            return
        try:
            amount = self.amount_edit.text_value()
        except MoneyError as exc:
            self.set_error(str(exc))
            return
        try:
            self.service.transfers.add(
                int(from_id), int(to_id), amount, _to_date(self.date_edit), self.note_edit.text()
            )
        except FinanceError as exc:
            self.set_error(str(exc))
            return
        self.service.after_change()
        self.accept()


# --------------------------------------------------------------------------
# 资金分区
# --------------------------------------------------------------------------
class AccountDialog(FinanceDialog):
    def __init__(self, service, *, account=None, parent=None) -> None:
        editing = account is not None
        super().__init__(
            "编辑资金分区" if editing else "新增资金分区",
            "资金分区用来区分手里的钱分别属于什么用途，名字可以自己起。",
            parent=parent,
            width=480,
        )
        self.service = service
        self.account = account

        name_row = QHBoxLayout()
        name_row.addWidget(self.field_label("名称"))
        name_row.addStretch(1)
        self.name_edit = QLineEdit(account.name if editing else "")
        self.name_edit.setFixedWidth(300)
        self.name_edit.setPlaceholderText("例如：吃饭预算 / 游戏基金")
        name_row.addWidget(self.name_edit)
        self.body.addLayout(name_row)

        note_row = QHBoxLayout()
        note_row.addWidget(self.field_label("备注"))
        note_row.addStretch(1)
        self.note_edit = QLineEdit(account.note if editing else "")
        self.note_edit.setFixedWidth(300)
        self.note_edit.setPlaceholderText("用途说明，选填")
        note_row.addWidget(self.note_edit)
        self.body.addLayout(note_row)

        if editing:
            info = QLabel(
                f"当前余额 {service.money(service.accounts.balance(account.id))} · "
                f"创建于 {account.created_text}"
            )
            info.setObjectName("Muted")
            self.body.addWidget(info)
        else:
            hint = QLabel("新分区的金额从 0 开始，之后用「资金调动」从其它分区转入。")
            hint.setObjectName("Muted")
            hint.setWordWrap(True)
            self.body.addWidget(hint)

        self.add_cancel()
        self.add_primary("保存")
        self.name_edit.setFocus()

    def _on_primary(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.set_error("请填写资金分区名称。")
            return
        try:
            if self.account is None:
                self.service.accounts.create(name, note=self.note_edit.text())
            else:
                self.service.accounts.update(
                    self.account.id, name=name, note=self.note_edit.text()
                )
        except FinanceError as exc:
            self.set_error(str(exc))
            return
        self.service.after_change()
        self.accept()


# --------------------------------------------------------------------------
# 分类明细 / 账户流水
# --------------------------------------------------------------------------
class FlowListDialog(FinanceDialog):
    """通用的流水列表对话框。"""

    def __init__(self, service, title: str, subtitle: str, parent=None, width=620) -> None:
        super().__init__(title, subtitle, parent=parent, width=width)
        self.service = service
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(2)
        self.container_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        self.scroll.setMinimumHeight(320)
        self.body.addWidget(self.scroll)
        self.add_cancel("关闭")
        self.footer.addStretch(1)


class CategoryTransactionsDialog(FlowListDialog):
    def __init__(self, service, month: str, category: str, parent=None) -> None:
        label = CATEGORY_LABELS.get(category, category)
        super().__init__(
            service,
            f"{label} · {month_display(month)}",
            "点击任意一条可以修改或删除，修改后余额和月报会立即更新。",
            parent=parent,
        )
        items = service.transactions.category_transactions(month, category)
        total = sum(item.amount_cents for item in items)
        header = QLabel(f"共 {len(items)} 笔，合计 {service.money(total)}")
        header.setObjectName("Muted")
        self.body.insertWidget(0, header)
        if not items:
            empty = QLabel("这个分类本月还没有支出。")
            empty.setObjectName("Muted")
            self.container_layout.insertWidget(0, empty)
            return
        for item in items:
            row = FlowRow()
            row.set_transaction(item, service.money)
            row.edit_requested.connect(self._edit)
            self.container_layout.insertWidget(self.container_layout.count() - 1, row)

    def _edit(self, transaction_id: int) -> None:
        try:
            transaction = self.service.transactions.get(transaction_id)
        except FinanceError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))
            return
        dialog = TransactionDialog(self.service, transaction=transaction, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.accept()


class AccountDetailDialog(FlowListDialog):
    def __init__(self, service, account_id: int, parent=None) -> None:
        account = service.accounts.get(account_id)
        balance = service.accounts.balance(account_id)
        super().__init__(
            service,
            account.name,
            f"当前余额 {service.money(balance)} · 创建于 {account.created_text}"
            + (f" · {account.note}" if account.note else ""),
            parent=parent,
            width=640,
        )
        self.account_id = account_id
        rows = service.accounts.balances(include_archived=True)
        target = next((row for row in rows if row.account.id == account_id), None)
        opening = account.opening_cents
        income = expense = transfer_in = transfer_out = 0
        if target is not None:
            opening = target.opening_cents
            income = target.income_cents
            expense = target.expense_cents
            transfer_in = target.transfer_in_cents
            transfer_out = target.transfer_out_cents
        info = QLabel(
            f"开户 {service.money(opening)} · 收入 {service.money(income)} · "
            f"支出 {service.money(expense)} · 转入 {service.money(transfer_in)} · "
            f"转出 {service.money(transfer_out)}"
        )
        info.setObjectName("Muted")
        self.body.insertWidget(0, info)
        flows = service.accounts.flows(account_id)
        if not flows:
            empty = QLabel("这个分区还没有任何流水。")
            empty.setObjectName("Muted")
            self.container_layout.insertWidget(0, empty)
            return
        for flow in flows:
            row = QFrame()
            row.setObjectName("FinanceRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 7, 10, 7)
            layout.setSpacing(10)
            title = QLabel(flow["label"])
            title.setObjectName("RowTitle")
            layout.addWidget(title, 1)
            date_label = QLabel(str(flow["occurred_on"]))
            date_label.setObjectName("Muted")
            layout.addWidget(date_label)
            amount = QLabel(("+" if flow["delta"] > 0 else "−") + service.money(abs(flow["delta"])))
            amount.setObjectName("AmountPositive" if flow["delta"] > 0 else "AmountNegative")
            amount.setMinimumWidth(100)
            amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(amount)
            self.container_layout.insertWidget(self.container_layout.count() - 1, row)


# --------------------------------------------------------------------------
# 财务设置
# --------------------------------------------------------------------------
class FinanceSettingsDialog(FinanceDialog):
    def __init__(self, service, parent=None) -> None:
        super().__init__(
            "财务设置",
            "这些设置只影响记账模块，不会改动日程与提醒。",
            parent=parent,
            width=520,
        )
        self.service = service

        currency_row = QHBoxLayout()
        currency_row.addWidget(self.field_label("货币单位"))
        currency_row.addStretch(1)
        self.currency_combo = QComboBox()
        for code, (symbol, decimals, name) in CURRENCIES.items():
            self.currency_combo.addItem(f"{name}（{symbol}）", code)
        index = self.currency_combo.findData(service.settings.currency)
        if index >= 0:
            self.currency_combo.setCurrentIndex(index)
        currency_row.addWidget(self.currency_combo)
        self.body.addLayout(currency_row)

        hint = QLabel("切换货币只改变显示符号与小数位，已记录的数字不会换算。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        self.body.addWidget(hint)

        self.negative_check = QCheckBox("允许多个资金分区出现负余额")
        self.negative_check.setChecked(service.settings.allow_negative)
        self.body.addWidget(self.negative_check)
        negative_hint = QLabel("默认不允许支出把分区余额花成负数；开启后不再拦截。")
        negative_hint.setObjectName("Muted")
        negative_hint.setWordWrap(True)
        self.body.addWidget(negative_hint)

        if is_editable_categories():
            self.body.addSpacing(4)
            hint = QLabel("支出分类：默认的六个分类可以改名或隐藏，也可以新增自己的分类。")
            hint.setObjectName("Muted")
            hint.setWordWrap(True)
            self.body.addWidget(hint)
            manage = QPushButton("管理支出分类…")
            manage.setObjectName("Ghost")
            manage.setCursor(Qt.CursorShape.PointingHandCursor)
            manage.clicked.connect(self._manage_categories)
            self.body.addWidget(manage, 0, Qt.AlignmentFlag.AlignLeft)

        self.body.addSpacing(6)
        line = QFrame()
        line.setObjectName("Separator")
        line.setFixedHeight(1)
        self.body.addWidget(line)

        data_row = QHBoxLayout()
        data_row.addWidget(self.field_label("数据"))
        data_row.addStretch(1)
        backup = QPushButton("备份")
        backup.setObjectName("Ghost")
        backup.clicked.connect(self._backup)
        data_row.addWidget(backup)
        restore = QPushButton("恢复")
        restore.setObjectName("Ghost")
        restore.clicked.connect(self._restore)
        data_row.addWidget(restore)
        export = QPushButton("导出 CSV")
        export.setObjectName("Ghost")
        export.clicked.connect(self._export)
        data_row.addWidget(export)
        self.body.addLayout(data_row)

        path_label = QLabel(f"记账数据文件：{service.db.path}")
        path_label.setObjectName("Muted")
        path_label.setWordWrap(True)
        self.body.addWidget(path_label)

        self.add_cancel()
        self.add_primary("保存")

    def _on_primary(self) -> None:
        code = self.currency_combo.currentData()
        self.service.settings.set_currency(code)
        self.service.settings.set_allow_negative(self.negative_check.isChecked())
        self.service.settings.reload()
        self.accept()

    def _manage_categories(self) -> None:
        dialog = CategoryManagerDialog(self.service, parent=self)
        dialog.exec()

    def _backup(self) -> None:
        default = str(Path.home() / "Documents" / f"记账备份-{datetime.now():%Y%m%d}.db")
        path, _ = QFileDialog.getSaveFileName(
            self, "备份记账数据", default, "记账数据库 (*.db)"
        )
        if not path:
            return
        try:
            self.service.backup_to(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "备份失败", str(exc))
            return
        QMessageBox.information(self, "备份完成", f"已备份到：\n{path}")

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择记账备份", str(Path.home() / "Documents"), "记账数据库 (*.db)"
        )
        if not path:
            return
        if not self.confirm(
            "恢复记账数据",
            "恢复会用备份文件覆盖当前的记账数据，日程数据不受影响。\n当前数据会先自动另存一份。确定继续？",
        ):
            return
        try:
            self.service.restore_from(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "恢复失败", str(exc))
            return
        QMessageBox.information(self, "恢复完成", "记账数据已恢复。")
        self.accept()

    def _export(self) -> None:
        default = str(Path.home() / "Documents" / f"记账明细-{datetime.now():%Y%m%d}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "导出记账明细", default, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            self.service.export_csv(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")


# --------------------------------------------------------------------------
# 支出分类管理（自定义分类版）
# --------------------------------------------------------------------------
class CategoryManagerDialog(FinanceDialog):
    def __init__(self, service, parent=None) -> None:
        super().__init__(
            "支出分类",
            "可以新增分类、给分类改名，或把不用的分类隐藏起来。"
            "隐藏只是不再出现在记账选择里，历史账目和月报仍按原分类统计。",
            parent=parent,
            width=520,
        )
        self.service = service
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(260)
        self.body.addWidget(self.list_widget)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        add_button = QPushButton("新增分类")
        add_button.setObjectName("Primary")
        add_button.clicked.connect(self._add)
        buttons.addWidget(add_button)
        rename_button = QPushButton("重命名")
        rename_button.clicked.connect(self._rename)
        buttons.addWidget(rename_button)
        self.toggle_button = QPushButton("隐藏")
        self.toggle_button.clicked.connect(self._toggle_hidden)
        buttons.addWidget(self.toggle_button)
        buttons.addStretch(1)
        self.body.addLayout(buttons)
        self.list_widget.currentItemChanged.connect(self._on_selection)
        self._reload()
        self.add_cancel("关闭")

    def _reload(self) -> None:
        current = self.list_widget.currentItem()
        key = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.list_widget.clear()
        for category in self.service.categories.list():
            count = self.service.categories.usage(category.key)
            suffix = "（已隐藏）" if category.hidden else ""
            item = QListWidgetItem(f"{category.label}{suffix}    {count} 笔")
            item.setIcon(finance_icons.category_icon(category.key, category.color, 16))
            item.setData(Qt.ItemDataRole.UserRole, category.key)
            self.list_widget.addItem(item)
            if category.key == key:
                self.list_widget.setCurrentItem(item)
        if self.list_widget.currentItem() is None and self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self._on_selection(self.list_widget.currentItem())

    def _on_selection(self, item) -> None:
        if item is None:
            self.toggle_button.setEnabled(False)
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        category = self.service.categories.get(key)
        self.toggle_button.setEnabled(True)
        self.toggle_button.setText("显示" if category.hidden else "隐藏")

    def _selected_key(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _add(self) -> None:
        label, ok = QInputDialog.getText(self, "新增支出分类", "分类名称：")
        if not ok:
            return
        try:
            key = self.service.categories.add(label)
        except FinanceError as exc:
            QMessageBox.warning(self, "无法新增", str(exc))
            return
        self._reload()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self.list_widget.setCurrentRow(row)
                break

    def _rename(self) -> None:
        key = self._selected_key()
        if key is None:
            return
        category = self.service.categories.get(key)
        label, ok = QInputDialog.getText(
            self, "重命名分类", "分类名称：", text=category.label
        )
        if not ok:
            return
        try:
            self.service.categories.rename(key, label)
        except FinanceError as exc:
            QMessageBox.warning(self, "无法重命名", str(exc))
            return
        self._reload()

    def _toggle_hidden(self) -> None:
        key = self._selected_key()
        if key is None:
            return
        category = self.service.categories.get(key)
        try:
            self.service.categories.set_hidden(key, not category.hidden)
        except FinanceError as exc:
            QMessageBox.warning(self, "无法修改", str(exc))
            return
        self._reload()
