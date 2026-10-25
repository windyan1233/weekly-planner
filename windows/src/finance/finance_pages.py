"""记账模块的三个页面：记账首页、月度总结、资金管理。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..edition import editable_categories as is_editable_categories
from . import finance_icons
from .finance_models import (
    CATEGORIES,
    EXPENSE,
    INCOME,
    month_display,
    month_of_today,
    shift_month,
)
from .finance_widgets import (
    CategoryRow,
    ClickableFrame,
    DonutChart,
    EmptyState,
    FlowRow,
    Pill,
    RatioBar,
    SectionCard,
    SegmentedControl,
    StatCard,
    _repolish,
)


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def _scroll_page() -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 6, 4)
    body_layout.setSpacing(12)
    scroll.setWidget(body)
    return scroll, body_layout


def _link_button(text: str, parent: QWidget | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("Link")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFlat(True)
    return button


# ==========================================================================
# 记账首页
# ==========================================================================
class OverviewPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.service = controller.service
        self._month = month_of_today()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.stack.addWidget(self._build_empty_page())
        self.stack.addWidget(self._build_content_page())

    # ------------------------------------------------------------------
    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 40, 30, 40)
        card_layout.setSpacing(10)
        card_layout.addWidget(
            EmptyState(
                "还没有开始记账",
                "先设置你现在手里的总金额，再把它分到几个资金分区。\n"
                "之后每次收入、支出都会实时更新总余额和月度总结。",
                icon=finance_icons.finance_icon("wallet", "#5B6BD6", 44),
            )
        )
        button = QPushButton("设置初始余额")
        button.setObjectName("Primary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.controller.open_initialize_dialog)
        card_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_content_page(self) -> QWidget:
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        scroll, self.content_layout = _scroll_page()
        wrapper_layout.addWidget(scroll)

        self.content_layout.addWidget(self._build_header())
        self.content_layout.addLayout(self._build_stats())
        self.content_layout.addLayout(self._build_body())
        self.content_layout.addStretch(1)
        return wrapper

    def _build_header(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 12, 16, 12)
        layout.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("记账")
        title.setObjectName("Title")
        title_box.addWidget(title)
        self.month_caption = QLabel("")
        self.month_caption.setObjectName("Muted")
        title_box.addWidget(self.month_caption)
        layout.addLayout(title_box)
        layout.addStretch(1)

        self.prev_month = QPushButton("‹")
        self.prev_month.setObjectName("IconButton")
        self.prev_month.setFixedSize(30, 30)
        self.prev_month.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_month.clicked.connect(lambda: self._shift_month(-1))
        layout.addWidget(self.prev_month)

        self.month_label = QLabel("")
        self.month_label.setObjectName("RowTitle")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setMinimumWidth(112)
        layout.addWidget(self.month_label)

        self.next_month = QPushButton("›")
        self.next_month.setObjectName("IconButton")
        self.next_month.setFixedSize(30, 30)
        self.next_month.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_month.clicked.connect(lambda: self._shift_month(1))
        layout.addWidget(self.next_month)

        this_month = QPushButton("本月")
        this_month.setObjectName("Ghost")
        this_month.setCursor(Qt.CursorShape.PointingHandCursor)
        this_month.clicked.connect(lambda: self._set_month(month_of_today()))
        layout.addWidget(this_month)

        layout.addSpacing(6)
        income_button = QPushButton("记一笔收入")
        income_button.setObjectName("IncomeButton")
        income_button.setIcon(finance_icons.finance_icon("income", "#3F8A67", 16))
        income_button.setCursor(Qt.CursorShape.PointingHandCursor)
        income_button.clicked.connect(lambda: self.controller.open_transaction_dialog(INCOME))
        layout.addWidget(income_button)

        expense_button = QPushButton("记一笔支出")
        expense_button.setObjectName("ExpenseButton")
        expense_button.setIcon(finance_icons.finance_icon("expense", "#B8525D", 16))
        expense_button.setCursor(Qt.CursorShape.PointingHandCursor)
        expense_button.clicked.connect(lambda: self.controller.open_transaction_dialog(EXPENSE))
        layout.addWidget(expense_button)

        transfer_button = QPushButton("资金调动")
        transfer_button.setObjectName("Ghost")
        transfer_button.setIcon(finance_icons.finance_icon("transfer", "#8A91A6", 16))
        transfer_button.setCursor(Qt.CursorShape.PointingHandCursor)
        transfer_button.clicked.connect(self.controller.open_transfer_dialog)
        layout.addWidget(transfer_button)
        return card

    def _build_stats(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        big = QFrame()
        big.setObjectName("Card")
        big_layout = QVBoxLayout(big)
        big_layout.setContentsMargins(20, 14, 20, 16)
        big_layout.setSpacing(4)
        big_title = QLabel("当前总余额")
        big_title.setObjectName("Muted")
        big_layout.addWidget(big_title)
        self.balance_label = QLabel("—")
        self.balance_label.setObjectName("BalanceValue")
        big_layout.addWidget(self.balance_label)
        self.balance_sub = QLabel("")
        self.balance_sub.setObjectName("Muted")
        self.balance_sub.setWordWrap(True)
        big_layout.addWidget(self.balance_sub)
        row.addWidget(big, 2)

        self.income_card = StatCard("本月收入", icon=finance_icons.finance_icon("income", "#4C9E78", 15))
        self.expense_card = StatCard("本月支出", icon=finance_icons.finance_icon("expense", "#D2606B", 15))
        self.net_card = StatCard("本月结余", icon=finance_icons.finance_icon("chart", "#5B6BD6", 15))
        for card in (self.income_card, self.expense_card, self.net_card):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(card, 1)
        column.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.opening_card = StatCard("本月初始余额", compact=True)
        self.closing_card = StatCard("本月末余额", compact=True)
        self.count_card = StatCard("本月账目", compact=True)
        for card in (self.opening_card, self.closing_card, self.count_card):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row2.addWidget(card)
        column.addLayout(row2)
        return column

    def _build_body(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(12)
        editable = is_editable_categories()
        self.category_card = SectionCard(
            "本月支出分类",
            subtitle=(
                "分类合计 = 本月总支出"
                if editable
                else "六个分类合计 = 本月总支出"
            ),
        )
        self.category_rows: list[CategoryRow] = []
        self.category_box = QVBoxLayout()
        self.category_box.setSpacing(2)
        self.category_card.body.addLayout(self.category_box)

        total_row = QHBoxLayout()
        self.category_total_label = QLabel("分类合计" if editable else "六类合计")
        total_row.addWidget(self.category_total_label)
        total_row.addStretch(1)
        self.category_total = QLabel("—")
        self.category_total.setObjectName("CategoryAmount")
        total_row.addWidget(self.category_total)
        self.category_card.body.addLayout(total_row)
        left.addWidget(self.category_card)

        self.recent_card = SectionCard("最近账目", subtitle="点击任意一条可以修改或删除")
        view_all = _link_button("查看月度明细")
        view_all.clicked.connect(lambda: self.controller.open_report(self._month))
        self.recent_card.header_layout.addWidget(view_all)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(2)
        self.recent_card.body.addLayout(self.recent_box)
        left.addWidget(self.recent_card)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(12)
        self.funds_card = SectionCard("资金分区", subtitle="所有分区余额之和 = 当前总余额")
        manage = _link_button("管理资金")
        manage.clicked.connect(lambda: self.controller.navigate("accounts"))
        self.funds_card.header_layout.addWidget(manage)
        self.funds_box = QVBoxLayout()
        self.funds_box.setSpacing(6)
        self.funds_card.body.addLayout(self.funds_box)
        right.addWidget(self.funds_card)
        right.addStretch(1)

        row.addLayout(left, 3)
        row.addLayout(right, 2)
        return row

    # ------------------------------------------------------------------
    def _shift_month(self, offset: int) -> None:
        self._set_month(shift_month(self._month, offset))

    def _set_month(self, month: str) -> None:
        self._month = month
        self.refresh()

    def month(self) -> str:
        return self._month

    def refresh(self) -> None:
        if not self.service.is_initialized():
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        overview = self.service.overview(self._month)
        money = self.service.money
        self.month_label.setText(month_display(self._month))
        self.month_caption.setText(
            f"{month_display(self._month)} · 本月 {overview.transaction_count} 笔账目"
        )
        self.balance_label.setText(money(overview.total_balance_cents))
        self.balance_sub.setText(
            f"初始 {money(overview.opening_total_cents)} · "
            f"累计收入 {money(overview.cumulative_income_cents)} · "
            f"累计支出 {money(overview.cumulative_expense_cents)}"
        )
        self.income_card.set_value(money(overview.income_cents), "in")
        self.income_card.set_sub(f"本月 {overview.transaction_count} 笔账目中的收入")
        self.expense_card.set_value(money(overview.expense_cents), "out")
        self.expense_card.set_sub(
            ("分类合计" if is_editable_categories() else "六个分类合计")
            if overview.expense_cents
            else "本月还没有支出"
        )
        self.net_card.set_value(
            money(overview.net_cents), "in" if overview.net_cents >= 0 else "out"
        )
        self.net_card.set_sub("收入 − 支出")
        self.opening_card.set_value(money(overview.opening_cents), "muted")
        self.opening_card.set_sub("上月结转而来的余额")
        self.closing_card.set_value(money(overview.closing_cents), "muted")
        self.closing_card.set_sub("自动结转到下月")
        self.count_card.set_value(f"{overview.transaction_count} 笔", "muted")
        self.count_card.set_sub("本月新增账目")

        clear_layout(self.category_box)
        self.category_rows = []
        total = 0
        for stat in overview.categories:
            row = CategoryRow(self.controller.palette)
            row.set_data(stat, money)
            row.clicked.connect(
                lambda key=stat.key: self.controller.open_category_dialog(self._month, key)
            )
            self.category_box.addWidget(row)
            self.category_rows.append(row)
            total += stat.amount_cents
        self.category_total.setText(money(total))

        clear_layout(self.recent_box)
        if not overview.recent:
            hint = QLabel("还没有账目，点右上角「记一笔收入 / 支出」开始。")
            hint.setObjectName("Muted")
            self.recent_box.addWidget(hint)
        else:
            for transaction in overview.recent:
                row = FlowRow()
                row.set_transaction(transaction, money)
                row.edit_requested.connect(self.controller.open_transaction_by_id)
                self.recent_box.addWidget(row)

        clear_layout(self.funds_box)
        total_balance = max(overview.total_balance_cents, 1)
        if not overview.account_balances:
            hint = QLabel("还没有资金分区。")
            hint.setObjectName("Muted")
            self.funds_box.addWidget(hint)
        else:
            for balance in overview.account_balances[:6]:
                self.funds_box.addWidget(self._fund_row(balance, total_balance, money))
            if len(overview.account_balances) > 6:
                more = QLabel(f"还有 {len(overview.account_balances) - 6} 个分区…")
                more.setObjectName("Muted")
                self.funds_box.addWidget(more)

    def _fund_row(self, balance, total_balance: int, money) -> QWidget:
        row = QFrame()
        row.setObjectName("FinanceRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        top = QHBoxLayout()
        name = QLabel(balance.name)
        name.setObjectName("RowTitle")
        top.addWidget(name)
        if balance.account.archived:
            top.addWidget(Pill("已归档"))
        top.addStretch(1)
        value = QLabel(money(balance.balance_cents))
        value.setObjectName("CategoryAmount")
        top.addWidget(value)
        layout.addLayout(top)
        bar = RatioBar()
        bar.set_palette(self.controller.palette)
        share = balance.balance_cents / total_balance * 100 if total_balance > 0 else 0
        bar.set_value(max(0.0, min(100.0, share)), "#5B6BD6")
        layout.addWidget(bar)
        return row

    def apply_palette(self, palette) -> None:
        for row in self.category_rows:
            row.set_palette(palette)
        for index in range(self.funds_box.count()):
            widget = self.funds_box.itemAt(index).widget()
            if widget is not None:
                for bar in widget.findChildren(RatioBar):
                    bar.set_palette(palette)


# ==========================================================================
# 月度总结
# ==========================================================================
class ReportPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.service = controller.service
        self._month = month_of_today()
        self._flow_mode = EXPENSE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(12)
        history_panel = QFrame()
        history_panel.setObjectName("Card")
        history_panel.setFixedWidth(250)
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(12, 12, 12, 10)
        history_layout.setSpacing(8)
        history_title = QLabel("历史月份")
        history_title.setObjectName("SectionTitle")
        history_layout.addWidget(history_title)
        history_hint = QLabel("点击查看完整月报")
        history_hint.setObjectName("Muted")
        history_layout.addWidget(history_hint)
        self.history_scroll, self.history_layout = _scroll_page()
        self.history_scroll.setWidgetResizable(True)
        history_layout.addWidget(self.history_scroll, 1)
        body.addWidget(history_panel)

        self.detail_scroll, self.detail_layout = _scroll_page()
        body.addWidget(self.detail_scroll, 1)
        layout.addLayout(body, 1)

    def _build_header(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 12, 16, 12)
        layout.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("月度总结")
        title.setObjectName("Title")
        title_box.addWidget(title)
        caption = QLabel("每月自动生成；以账目明细为准，随时可以回看历史")
        caption.setObjectName("Muted")
        title_box.addWidget(caption)
        layout.addLayout(title_box)
        layout.addStretch(1)

        self.year_combo = QComboBox()
        self.year_combo.setFixedWidth(92)
        layout.addWidget(self.year_combo)
        self.month_combo = QComboBox()
        self.month_combo.setFixedWidth(78)
        layout.addWidget(self.month_combo)

        prev = QPushButton("‹")
        prev.setObjectName("IconButton")
        prev.setFixedSize(30, 30)
        prev.setCursor(Qt.CursorShape.PointingHandCursor)
        prev.clicked.connect(lambda: self._set_month(shift_month(self._month, -1)))
        layout.addWidget(prev)
        nxt = QPushButton("›")
        nxt.setObjectName("IconButton")
        nxt.setFixedSize(30, 30)
        nxt.setCursor(Qt.CursorShape.PointingHandCursor)
        nxt.clicked.connect(lambda: self._set_month(shift_month(self._month, 1)))
        layout.addWidget(nxt)
        this_month = QPushButton("本月")
        this_month.setObjectName("Ghost")
        this_month.setCursor(Qt.CursorShape.PointingHandCursor)
        this_month.clicked.connect(lambda: self._set_month(month_of_today()))
        layout.addWidget(this_month)

        self.year_combo.currentIndexChanged.connect(self._on_combo_changed)
        self.month_combo.currentIndexChanged.connect(self._on_combo_changed)
        self._syncing = False
        return card

    def _on_combo_changed(self) -> None:
        if self._syncing:
            return
        year = self.year_combo.currentData()
        month = self.month_combo.currentData()
        if year is None or month is None:
            return
        self._set_month(f"{int(year):04d}-{int(month):02d}")

    def _set_month(self, month: str) -> None:
        self._month = month
        self.refresh()

    def month(self) -> str:
        return self._month

    def refresh(self) -> None:
        self._sync_combos()
        self._render_history()
        self._render_detail()

    def _sync_combos(self) -> None:
        cards = self.service.month_cards()
        months = [card.month for card in cards] or [month_of_today()]
        if self._month not in months:
            months = sorted(set(months + [self._month]))
        years = sorted({int(month[:4]) for month in months})
        current_year = int(self._month[:4])
        if current_year not in years:
            years.append(current_year)
            years.sort()
        self._syncing = True
        try:
            self.year_combo.clear()
            for year in years:
                self.year_combo.addItem(f"{year} 年", year)
            self.year_combo.setCurrentIndex(years.index(current_year))
            self.month_combo.clear()
            for month in range(1, 13):
                self.month_combo.addItem(f"{month} 月", month)
            self.month_combo.setCurrentIndex(int(self._month[5:7]) - 1)
        finally:
            self._syncing = False

    def _render_history(self) -> None:
        clear_layout(self.history_layout)
        cards = self.service.month_cards()
        if not cards:
            hint = QLabel("还没有月份记录")
            hint.setObjectName("Muted")
            self.history_layout.addWidget(hint)
            self.history_layout.addStretch(1)
            return
        money = self.service.money
        for card in cards:
            frame = ClickableFrame()
            frame.setObjectName("HistoryCard")
            frame.setProperty("selected", card.month == self._month)
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(12, 9, 12, 9)
            layout.setSpacing(3)
            top = QHBoxLayout()
            label = QLabel(month_display(card.month))
            label.setObjectName("RowTitle")
            top.addWidget(label)
            top.addStretch(1)
            if card.is_current:
                top.addWidget(Pill("本月"))
            layout.addLayout(top)
            flow = QLabel(
                f"收入 {money(card.income_cents)} · 支出 {money(card.expense_cents)}"
            )
            flow.setObjectName("Muted")
            layout.addWidget(flow)
            closing = QLabel(f"月末 {money(card.closing_cents)}")
            closing.setObjectName("HistoryClosing")
            layout.addWidget(closing)
            frame.clicked.connect(lambda m=card.month: self._set_month(m))
            self.history_layout.addWidget(frame)
        self.history_layout.addStretch(1)

    def _render_detail(self) -> None:
        clear_layout(self.detail_layout)
        report = self.service.report(self._month)
        money = self.service.money

        title_row = QHBoxLayout()
        title = QLabel(month_display(self._month))
        title.setObjectName("Title")
        title_row.addWidget(title)
        if report.is_current:
            title_row.addWidget(Pill("本月进行中"))
        title_row.addStretch(1)
        status = QLabel(
            f"月报已生成：{report.generated_at:%Y-%m-%d %H:%M}" if report.generated_at else "月报将在月末自动生成"
        )
        status.setObjectName("Muted")
        title_row.addWidget(status)
        self.detail_layout.addLayout(title_row)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        cards = [
            ("月初余额", report.opening_cents, "muted"),
            ("本月收入", report.income_cents, "in"),
            ("本月支出", report.expense_cents, "out"),
            ("本月净收支", report.net_cents, "in" if report.net_cents >= 0 else "out"),
            ("月末余额", report.closing_cents, "muted"),
        ]
        for title_text, cents, tone in cards:
            card = StatCard(title_text, compact=True)
            card.set_value(money(cents), tone)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cards_row.addWidget(card)
        self.detail_layout.addLayout(cards_row)

        self.detail_layout.addWidget(self._build_category_section(report, money))
        self.detail_layout.addWidget(self._build_account_section(report, money))
        self.detail_layout.addWidget(self._build_summary_section(report))
        self.detail_layout.addWidget(self._build_flow_section(report, money))
        self.detail_layout.addStretch(1)

    def _build_category_section(self, report, money) -> QWidget:
        card = SectionCard(
            "支出分类",
            subtitle=(
                "各分类合计必须等于本月总支出"
                if is_editable_categories()
                else "六个分类的合计必须等于本月总支出"
            ),
        )
        row = QHBoxLayout()
        row.setSpacing(16)
        donut = DonutChart()
        donut.set_palette(self.controller.palette)
        donut.set_data(
            [(stat.color, stat.amount_cents) for stat in report.categories],
            money(report.expense_cents),
        )
        row.addWidget(donut)
        column = QVBoxLayout()
        column.setSpacing(2)
        for stat in report.categories:
            category_row = CategoryRow(self.controller.palette)
            category_row.set_data(stat, money)
            category_row.clicked.connect(
                lambda key=stat.key: self.controller.open_category_dialog(self._month, key)
            )
            column.addWidget(category_row)
        total = QHBoxLayout()
        label = QLabel("分类合计" if is_editable_categories() else "六类合计")
        label.setObjectName("Muted")
        total.addWidget(label)
        total.addStretch(1)
        total_value = QLabel(money(report.category_total_cents))
        total_value.setObjectName("CategoryAmount")
        total.addWidget(total_value)
        check = QLabel(
            "✓ 与本月支出一致"
            if report.category_total_cents == report.expense_cents
            else "⚠ 与本月支出一致性异常"
        )
        check.setObjectName("Muted" if report.category_total_cents == report.expense_cents else "ErrorLabel")
        total.addSpacing(8)
        total.addWidget(check)
        column.addLayout(total)
        row.addLayout(column, 1)
        card.body.addLayout(row)
        return card

    def _build_account_section(self, report, money) -> QWidget:
        card = SectionCard("资金分区月末总结", subtitle="各分区月末余额合计 = 全局月末余额")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        headers = ["资金分区", "月初", "收入", "支出", "转入", "转出", "月末"]
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("Muted")
            if column == 0:
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            else:
                label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(label, 0, column)
        for index, row in enumerate(report.accounts, start=1):
            name = row.name + ("（已归档）" if row.archived else "")
            name_label = QLabel(name)
            name_label.setObjectName("RowTitle")
            grid.addWidget(name_label, index, 0)
            values = [
                row.opening_cents,
                row.income_cents,
                row.expense_cents,
                row.transfer_in_cents,
                row.transfer_out_cents,
                row.closing_cents,
            ]
            for column, cents in enumerate(values, start=1):
                label = QLabel(money(cents))
                label.setObjectName("CategoryAmount" if column == 6 else "Muted")
                label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(label, index, column)
        total_index = len(report.accounts) + 1
        total_label = QLabel("合计")
        total_label.setObjectName("RowTitle")
        grid.addWidget(total_label, total_index, 0)
        total_value = QLabel(money(report.account_closing_total))
        total_value.setObjectName("CategoryAmount")
        total_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(total_value, total_index, 6)
        check = QLabel(
            "✓ 各分区月末余额合计与全局月末余额一致"
            if report.account_closing_total == report.closing_cents
            else "⚠ 各分区月末余额合计与全局月末余额不一致"
        )
        check.setObjectName(
            "Muted" if report.account_closing_total == report.closing_cents else "ErrorLabel"
        )
        grid.setColumnStretch(0, 1)
        card.body.addLayout(grid)
        card.body.addWidget(check)
        return card

    def _build_summary_section(self, report) -> QWidget:
        card = SectionCard("本月总结", subtitle="根据真实账目自动生成")
        box = QFrame()
        box.setObjectName("SoftCard")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 12, 14, 12)
        text = QLabel(report.summary_text)
        text.setWordWrap(True)
        text.setObjectName("SummaryText")
        layout.addWidget(text)
        card.body.addWidget(box)
        return card

    def _build_flow_section(self, report, money) -> QWidget:
        card = SectionCard("本月明细", subtitle="收入、支出与资金调动")
        selector = SegmentedControl(
            [("expense", "支出"), ("income", "收入"), ("transfer", "资金调动")]
        )
        selector.set_current(self._flow_mode, emit=False)
        selector.changed.connect(self._on_flow_mode)
        card.header_layout.addWidget(selector)
        self.flow_box = QVBoxLayout()
        self.flow_box.setSpacing(2)
        card.body.addLayout(self.flow_box)
        self._fill_flows(report, money)
        return card

    def _on_flow_mode(self, mode: str) -> None:
        self._flow_mode = mode
        self.refresh()

    def _fill_flows(self, report, money) -> None:
        clear_layout(self.flow_box)
        if self._flow_mode == "transfer":
            if not report.transfers:
                hint = QLabel("本月没有资金调动。")
                hint.setObjectName("Muted")
                self.flow_box.addWidget(hint)
                return
            for transfer in report.transfers:
                row = QFrame()
                row.setObjectName("FinanceRow")
                layout = QHBoxLayout(row)
                layout.setContentsMargins(10, 8, 10, 8)
                layout.setSpacing(10)
                icon = QLabel()
                icon.setPixmap(finance_icons.finance_icon("transfer", "#5B6BD6", 20).pixmap(20, 20))
                layout.addWidget(icon)
                title = QLabel(f"{transfer.from_name} → {transfer.to_name}")
                title.setObjectName("RowTitle")
                layout.addWidget(title, 1)
                date_label = QLabel(f"{transfer.occurred_on:%m-%d}")
                date_label.setObjectName("Muted")
                layout.addWidget(date_label)
                amount = QLabel(money(transfer.amount_cents))
                amount.setObjectName("CategoryAmount")
                amount.setMinimumWidth(100)
                amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                layout.addWidget(amount)
                delete = QPushButton("删除")
                delete.setObjectName("DangerGhost")
                delete.setCursor(Qt.CursorShape.PointingHandCursor)
                delete.clicked.connect(
                    lambda _=False, transfer_id=transfer.id: self.controller.delete_transfer(transfer_id)
                )
                layout.addWidget(delete)
                self.flow_box.addWidget(row)
            return

        kind = "expense" if self._flow_mode == "expense" else "income"
        items = [item for item in report.transactions if item.kind == kind]
        if not items:
            hint = QLabel("本月没有这项记录。")
            hint.setObjectName("Muted")
            self.flow_box.addWidget(hint)
            return
        for transaction in items:
            row = FlowRow()
            row.set_transaction(transaction, money)
            row.edit_requested.connect(self.controller.open_transaction_by_id)
            self.flow_box.addWidget(row)

    def apply_palette(self, palette) -> None:
        for donut in self.findChildren(DonutChart):
            donut.set_palette(palette)
        for row in self.findChildren(CategoryRow):
            row.set_palette(palette)


# ==========================================================================
# 资金管理
# ==========================================================================
class AccountsPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.service = controller.service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_summary())

        self.scroll, self.grid_host = _scroll_page()
        self.cards_layout = QGridLayout()
        self.cards_layout.setHorizontalSpacing(12)
        self.cards_layout.setVerticalSpacing(12)
        self.grid_host.addLayout(self.cards_layout)
        self.grid_host.addStretch(1)
        layout.addWidget(self.scroll, 1)

    def _build_header(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 12, 16, 12)
        layout.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("资金管理")
        title.setObjectName("Title")
        title_box.addWidget(title)
        caption = QLabel("把总金额分成几个分区，名字由你决定；分区之间可以随时调动")
        caption.setObjectName("Muted")
        title_box.addWidget(caption)
        layout.addLayout(title_box)
        layout.addStretch(1)

        transfer = QPushButton("资金调动")
        transfer.setObjectName("Ghost")
        transfer.setIcon(finance_icons.finance_icon("transfer", "#8A91A6", 16))
        transfer.setCursor(Qt.CursorShape.PointingHandCursor)
        transfer.clicked.connect(self.controller.open_transfer_dialog)
        layout.addWidget(transfer)

        add = QPushButton("新增资金分区")
        add.setObjectName("Primary")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setIcon(finance_icons.finance_icon("coins", "#FFFFFF", 16))
        add.clicked.connect(self.controller.open_account_dialog)
        layout.addWidget(add)

        settings = QPushButton("财务设置")
        settings.setObjectName("Ghost")
        settings.setCursor(Qt.CursorShape.PointingHandCursor)
        settings.clicked.connect(self.controller.open_settings_dialog)
        layout.addWidget(settings)
        return card

    def _build_summary(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        label = QLabel("分区合计")
        label.setObjectName("Muted")
        layout.addWidget(label)
        self.total_label = QLabel("—")
        self.total_label.setObjectName("FinanceValueSm")
        layout.addWidget(self.total_label)
        layout.addStretch(1)

        self.consistency_label = QLabel("")
        self.consistency_label.setObjectName("Muted")
        layout.addWidget(self.consistency_label)
        return card

    def refresh(self) -> None:
        balances = self.service.accounts.balances(include_archived=True)
        money = self.service.money
        total = sum(item.balance_cents for item in balances)
        opening = self.service.accounts.opening_total()
        income, expense = self.service.totals()
        expected = opening + income - expense
        self.total_label.setText(money(total))
        if total == expected:
            self.consistency_label.setText(
                f"✓ 分区合计 = 初始 {money(opening)} + 收入 {money(income)} − 支出 {money(expense)}"
            )
            self.consistency_label.setObjectName("Muted")
        else:
            self.consistency_label.setText(
                f"⚠ 分区合计与账目推算不一致（推算 {money(expected)}），请检查数据"
            )
            self.consistency_label.setObjectName("ErrorLabel")
        _repolish(self.consistency_label)

        clear_layout(self.cards_layout)
        if not balances:
            empty = QFrame()
            empty.setObjectName("Card")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(24, 30, 24, 30)
            empty_layout.addWidget(
                EmptyState(
                    "还没有资金分区",
                    "先设置初始余额，或在初始化后新增分区并用「资金调动」分配资金。",
                    icon=finance_icons.finance_icon("layers", "#5B6BD6", 36),
                )
            )
            self.cards_layout.addWidget(empty, 0, 0, 1, 2)
            return
        for index, balance in enumerate(balances):
            card = self._account_card(balance, total, money)
            self.cards_layout.addWidget(card, index // 2, index % 2)
        if len(balances) % 2:
            filler = QWidget()
            filler.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.cards_layout.addWidget(filler, len(balances) // 2, 1)

    def _account_card(self, balance, total_balance: int, money) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        name = QLabel(balance.name)
        name.setObjectName("RowTitle")
        top.addWidget(name)
        if balance.account.archived:
            top.addWidget(Pill("已归档"))
        top.addStretch(1)
        share = balance.balance_cents / total_balance * 100 if total_balance else 0
        share_label = QLabel(f"{share:.1f}%")
        share_label.setObjectName("Muted")
        top.addWidget(share_label)
        layout.addLayout(top)

        value = QLabel(money(balance.balance_cents))
        value.setObjectName("FinanceValueSm")
        layout.addWidget(value)

        meta = QLabel(
            f"开户 {money(balance.opening_cents)} · 收入 {money(balance.income_cents)} · "
            f"支出 {money(balance.expense_cents)}"
        )
        meta.setObjectName("Muted")
        layout.addWidget(meta)
        if balance.transfer_in_cents or balance.transfer_out_cents:
            trans = QLabel(
                f"转入 {money(balance.transfer_in_cents)} · 转出 {money(balance.transfer_out_cents)}"
            )
            trans.setObjectName("Muted")
            layout.addWidget(trans)
        if balance.account.note:
            note = QLabel(balance.account.note)
            note.setObjectName("Muted")
            note.setWordWrap(True)
            layout.addWidget(note)

        footer = QHBoxLayout()
        footer.setSpacing(4)
        created = QLabel(f"创建于 {balance.account.created_text}")
        created.setObjectName("Muted")
        footer.addWidget(created)
        footer.addStretch(1)

        flow_button = QPushButton("流水")
        flow_button.setObjectName("Ghost")
        flow_button.setCursor(Qt.CursorShape.PointingHandCursor)
        flow_button.clicked.connect(
            lambda _=False, account_id=balance.account.id: self.controller.open_account_detail(account_id)
        )
        footer.addWidget(flow_button)

        edit_button = QPushButton("编辑")
        edit_button.setObjectName("Ghost")
        edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_button.clicked.connect(
            lambda _=False, account_id=balance.account.id: self.controller.open_account_dialog_by_id(account_id)
        )
        footer.addWidget(edit_button)

        if not balance.account.system:
            archive = QPushButton("启用" if balance.account.archived else "归档")
            archive.setObjectName("Ghost")
            archive.setCursor(Qt.CursorShape.PointingHandCursor)
            archive.clicked.connect(
                lambda _=False, account_id=balance.account.id, archived=balance.account.archived: (
                    self.controller.set_account_archived(account_id, not archived)
                )
            )
            footer.addWidget(archive)

            delete = QPushButton("删除")
            delete.setObjectName("DangerGhost")
            delete.setCursor(Qt.CursorShape.PointingHandCursor)
            delete.clicked.connect(
                lambda _=False, account_id=balance.account.id: self.controller.delete_account(account_id)
            )
            footer.addWidget(delete)

        layout.addLayout(footer)
        return card

    def apply_palette(self, palette) -> None:
        pass
