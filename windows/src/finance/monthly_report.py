"""月度总结：以账目明细为唯一事实来源，实时计算，并保存可追溯的月报快照。

* 月初余额 = 全局开户金额合计 + 该月之前所有账目的净额（转账不参与）。
* 月末余额 = 月初余额 + 本月收入 - 本月支出。
* 下月月初余额天然等于本月月末余额（同一公式推导），不需要写回任何余额。
* 因此补记/修改历史账目后，后续所有月份的余额与报表都会自动一致。
"""

from __future__ import annotations

import json
from datetime import datetime

from .account_manager import AccountManager
from .finance_database import FinanceDatabase
from .finance_models import (
    CATEGORIES,
    AccountMonthRow,
    CategoryStat,
    MonthCard,
    MonthReport,
    format_money,
    percent,
    month_key,
    month_bounds,
    shift_month,
)
from .transaction_manager import TransactionManager
from .transfer_manager import TransferManager


class MonthlyReportBuilder:
    def __init__(
        self,
        db: FinanceDatabase,
        accounts: AccountManager,
        transactions: TransactionManager,
        transfers: TransferManager,
        settings,
        categories=None,
    ) -> None:
        self.db = db
        self.accounts = accounts
        self.transactions = transactions
        self.transfers = transfers
        self.settings = settings
        self.categories = categories

    def _report_categories(self, totals: dict[str, int], prev_totals: dict[str, int]):
        """月报里展示的分类：可用分类 + 本月/上月有金额的隐藏分类。"""
        items = self.categories.list() if self.categories is not None else []
        if not items:
            from .finance_models import Category, CATEGORIES

            items = [
                Category(key=key, label=label, color=color, sort_order=index)
                for index, (key, label, color, _note) in enumerate(CATEGORIES)
            ]
        return [
            item
            for item in items
            if not item.hidden
            or totals.get(item.key, 0)
            or prev_totals.get(item.key, 0)
        ]

    # ------------------------------------------------------------------
    # 资金分区逐月汇总
    # ------------------------------------------------------------------
    def _account_net_before(self, month: str) -> dict[int, int]:
        start, _ = month_bounds(month)
        rows = self.db.query(
            """
            SELECT account_id, SUM(delta) AS total FROM (
                SELECT account_id,
                       CASE kind WHEN 'income' THEN amount_cents ELSE -amount_cents END AS delta
                FROM transactions WHERE occurred_on < ?
                UNION ALL
                SELECT from_account_id, -amount_cents FROM transfers WHERE occurred_on < ?
                UNION ALL
                SELECT to_account_id, amount_cents FROM transfers WHERE occurred_on < ?
            ) GROUP BY account_id
            """,
            (start.isoformat(), start.isoformat(), start.isoformat()),
        )
        return {int(row["account_id"]): int(row["total"] or 0) for row in rows}

    def _account_month_flows(self, month: str) -> dict[int, dict[str, int]]:
        start, end = month_bounds(month)
        flows: dict[int, dict[str, int]] = {}

        def bucket(account_id: int) -> dict[str, int]:
            return flows.setdefault(
                account_id,
                {"income": 0, "expense": 0, "transfer_in": 0, "transfer_out": 0},
            )

        for row in self.db.query(
            "SELECT account_id, kind, COALESCE(SUM(amount_cents), 0) AS total "
            "FROM transactions WHERE occurred_on >= ? AND occurred_on < ? GROUP BY account_id, kind",
            (start.isoformat(), end.isoformat()),
        ):
            bucket(int(row["account_id"]))[row["kind"]] = int(row["total"] or 0)
        for row in self.db.query(
            "SELECT to_account_id AS account_id, COALESCE(SUM(amount_cents), 0) AS total "
            "FROM transfers WHERE occurred_on >= ? AND occurred_on < ? GROUP BY to_account_id",
            (start.isoformat(), end.isoformat()),
        ):
            bucket(int(row["account_id"]))["transfer_in"] = int(row["total"] or 0)
        for row in self.db.query(
            "SELECT from_account_id AS account_id, COALESCE(SUM(amount_cents), 0) AS total "
            "FROM transfers WHERE occurred_on >= ? AND occurred_on < ? GROUP BY from_account_id",
            (start.isoformat(), end.isoformat()),
        ):
            bucket(int(row["account_id"]))["transfer_out"] = int(row["total"] or 0)
        return flows

    def account_rows(self, month: str) -> list[AccountMonthRow]:
        net_before = self._account_net_before(month)
        flows = self._account_month_flows(month)
        rows: list[AccountMonthRow] = []
        for account in self.accounts.list(include_archived=True):
            effect = flows.get(account.id, {})
            opening = account.opening_cents + net_before.get(account.id, 0)
            income = effect.get("income", 0)
            expense = effect.get("expense", 0)
            transfer_in = effect.get("transfer_in", 0)
            transfer_out = effect.get("transfer_out", 0)
            closing = opening + income - expense + transfer_in - transfer_out
            rows.append(
                AccountMonthRow(
                    account_id=account.id,
                    name=account.name,
                    opening_cents=opening,
                    income_cents=income,
                    expense_cents=expense,
                    transfer_in_cents=transfer_in,
                    transfer_out_cents=transfer_out,
                    closing_cents=closing,
                    archived=account.archived,
                )
            )
        return rows

    # ------------------------------------------------------------------
    # 月报
    # ------------------------------------------------------------------
    def global_opening(self) -> int:
        return self.accounts.opening_total()

    def opening_balance(self, month: str) -> int:
        return self.global_opening() + self.transactions.net_before(month)

    def report(self, month: str, *, now: datetime | None = None) -> MonthReport:
        now = now or datetime.now()
        current_month = month_key(now)
        income, expense = self.transactions.month_totals(month)
        opening = self.opening_balance(month)
        closing = opening + income - expense
        previous = shift_month(month, -1)
        prev_totals = self.transactions.category_totals(previous)
        totals = self.transactions.category_totals(month)
        categories: list[CategoryStat] = []
        for category in self._report_categories(totals, prev_totals):
            amount = totals.get(category.key, 0)
            categories.append(
                CategoryStat(
                    key=category.key,
                    label=category.label,
                    color=category.color,
                    amount_cents=amount,
                    ratio=percent(amount, expense),
                    prev_cents=prev_totals.get(category.key, 0),
                )
            )
        transactions = self.transactions.list(month=month)
        transfers = self.transfers.list(month=month)
        report = MonthReport(
            month=month,
            opening_cents=opening,
            income_cents=income,
            expense_cents=expense,
            net_cents=income - expense,
            closing_cents=closing,
            categories=categories,
            accounts=self.account_rows(month),
            transfers=transfers,
            transactions=transactions,
            is_current=(month == current_month),
            has_data=bool(transactions or transfers),
        )
        report.generated_at = self.snapshot_time(month)
        report.summary_text = self.summary_text(report)
        return report

    def summary_text(self, report: MonthReport) -> str:
        money = lambda cents: format_money(
            cents, self.settings.symbol, self.settings.decimals
        )
        if not report.has_data:
            if report.opening_cents or report.closing_cents:
                return (
                    f"本月没有新增收支记录，月初余额 {money(report.opening_cents)} 保持不变，"
                    f"月末剩余 {money(report.closing_cents)}，将自动结转至下月。"
                )
            return "本月还没有任何收支记录。"
        parts = [
            f"本月总收入为 {money(report.income_cents)}，"
            f"总支出为 {money(report.expense_cents)}，"
            f"净结余为 {money(report.net_cents)}。"
        ]
        top = report.top_category
        if top is not None and top.amount_cents > 0:
            parts.append(f"支出最多的类别是「{top.label}」，占总支出的 {top.ratio:.1f}%。")
        else:
            parts.append("本月没有支出记录。")
        parts.append(f"本月末剩余 {money(report.closing_cents)}，将自动结转至下月。")
        return "".join(parts)

    # ------------------------------------------------------------------
    # 月份列表
    # ------------------------------------------------------------------
    def history_months(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        current = month_key(now)
        first = self.transactions.first_month()
        if first is None:
            return [current] if self.accounts.count() else []
        months: list[str] = []
        cursor = current
        while cursor >= first:
            months.append(cursor)
            cursor = shift_month(cursor, -1)
        return months

    def month_cards(self, now: datetime | None = None) -> list[MonthCard]:
        now = now or datetime.now()
        cards: list[MonthCard] = []
        for month in self.history_months(now):
            income, expense = self.transactions.month_totals(month)
            closing = self.opening_balance(month) + income - expense
            cards.append(
                MonthCard(
                    month=month,
                    income_cents=income,
                    expense_cents=expense,
                    closing_cents=closing,
                    has_data=bool(
                        self.transactions.count(month=month) or self.transfers.list(month=month)
                    ),
                    is_current=(month == month_key(now)),
                )
            )
        return cards

    # ------------------------------------------------------------------
    # 月报快照（可追溯的生成记录）
    # ------------------------------------------------------------------
    def snapshot_time(self, month: str) -> datetime | None:
        row = self.db.query_one(
            "SELECT generated_at FROM monthly_reports WHERE month = ?", (month,)
        )
        if row is None:
            return None
        try:
            return datetime.strptime(row["generated_at"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def _payload(self, month: str) -> dict:
        income, expense = self.transactions.month_totals(month)
        return {
            "opening": self.opening_balance(month),
            "income": income,
            "expense": expense,
            "closing": self.opening_balance(month) + income - expense,
            "categories": self.transactions.category_totals(month),
            "accounts": [
                {
                    "id": row.account_id,
                    "name": row.name,
                    "opening": row.opening_cents,
                    "income": row.income_cents,
                    "expense": row.expense_cents,
                    "in": row.transfer_in_cents,
                    "out": row.transfer_out_cents,
                    "closing": row.closing_cents,
                }
                for row in self.account_rows(month)
            ],
        }

    def ensure_snapshots(self, now: datetime | None = None) -> int:
        """为已完成月份（以及当前月）补齐/刷新月报快照，返回写入的月份数。"""
        now = now or datetime.now()
        written = 0
        for month in self.history_months(now):
            payload = self._payload(month)
            existing = self.db.query_one(
                "SELECT * FROM monthly_reports WHERE month = ?", (month,)
            )
            if existing is not None:
                same = (
                    int(existing["opening_cents"]) == payload["opening"]
                    and int(existing["income_cents"]) == payload["income"]
                    and int(existing["expense_cents"]) == payload["expense"]
                    and int(existing["closing_cents"]) == payload["closing"]
                    and json.loads(existing["category_json"]) == payload["categories"]
                )
                if same:
                    continue
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.db.transaction():
                self.db.execute(
                    "INSERT INTO monthly_reports(month, opening_cents, income_cents, "
                    "expense_cents, closing_cents, category_json, account_json, generated_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(month) DO UPDATE SET opening_cents = excluded.opening_cents, "
                    "income_cents = excluded.income_cents, expense_cents = excluded.expense_cents, "
                    "closing_cents = excluded.closing_cents, category_json = excluded.category_json, "
                    "account_json = excluded.account_json, generated_at = excluded.generated_at",
                    (
                        month,
                        payload["opening"],
                        payload["income"],
                        payload["expense"],
                        payload["closing"],
                        json.dumps(payload["categories"], ensure_ascii=False, sort_keys=True),
                        json.dumps(payload["accounts"], ensure_ascii=False),
                        stamp,
                    ),
                )
            written += 1
        return written
