"""记账模块的对外接口（界面层只依赖这个类）。

职责边界：
* 日程模块不导入本模块；
* 本模块只读写 ``finance.db``；
* 所有余额由账目实时推导，报表也实时计算，快照只作为生成记录。
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .account_manager import AccountManager
from .finance_categories import CategoryRepository
from .finance_database import FinanceDatabase
from .finance_models import (
    CATEGORIES,
    EXPENSE,
    INCOME,
    CategoryStat,
    FinanceError,
    MonthCard,
    MonthReport,
    Overview,
    Transaction,
    format_money,
    month_key,
    percent,
    shift_month,
)
from .finance_settings import FinanceSettings
from .monthly_report import MonthlyReportBuilder
from .transaction_manager import TransactionManager
from .transfer_manager import TransferManager


class FinanceService:
    def __init__(
        self,
        path: str | Path,
        *,
        schedule_db_path: str | Path | None = None,
    ) -> None:
        self.db = FinanceDatabase(path, schedule_db_path=schedule_db_path)
        self.settings = FinanceSettings(self.db)
        self.accounts = AccountManager(self.db)
        self.categories = CategoryRepository(self.db)
        self.transactions = TransactionManager(
            self.db, self.accounts, self.settings, self.categories
        )
        self.transfers = TransferManager(self.db, self.accounts, self.settings)
        self.reports = MonthlyReportBuilder(
            self.db,
            self.accounts,
            self.transactions,
            self.transfers,
            self.settings,
            self.categories,
        )

    # ------------------------------------------------------------------
    # 显示辅助
    # ------------------------------------------------------------------
    def money(self, cents: int) -> str:
        return format_money(cents, self.settings.symbol, self.settings.decimals)

    @property
    def symbol(self) -> str:
        return self.settings.symbol

    @property
    def decimals(self) -> int:
        return self.settings.decimals

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def is_initialized(self) -> bool:
        return bool(self.settings.initialized_at) or self.accounts.count() > 0

    def initialize(
        self, total_cents: int, allocations: list[tuple[str, int, str]]
    ) -> None:
        """设定初始总金额并分配到各资金分区。"""
        if self.is_initialized():
            raise FinanceError("记账已经初始化过了。")
        total = int(total_cents)
        if total <= 0:
            raise FinanceError("初始总金额必须大于 0。")
        rows: list[tuple[str, int, str]] = []
        seen: set[str] = set()
        for name, cents, note in allocations:
            clean = (name or "").strip()
            if not clean:
                raise FinanceError("资金分区名称不能为空。")
            if len(clean) > 30:
                raise FinanceError("资金分区名称最多 30 个字。")
            if clean.lower() in seen:
                raise FinanceError(f"资金分区「{clean}」重复了。")
            seen.add(clean.lower())
            amount = int(cents)
            if amount < 0:
                raise FinanceError("分配金额不能是负数。")
            rows.append((clean, amount, (note or "").strip()))
        if not rows:
            raise FinanceError("至少需要一个资金分区。")
        allocated = sum(row[1] for row in rows)
        if allocated > total:
            raise FinanceError(
                f"分配金额合计 {self.money(allocated)} 超过了初始总金额 {self.money(total)}。"
            )
        remainder = total - allocated
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction():
            for name, amount, note in rows:
                if name == "未分配资金":
                    raise FinanceError("「未分配资金」是保留名称，请换一个名字。")
                self.db.execute(
                    "INSERT INTO accounts(name, note, opening_cents, created_at, archived, system) "
                    "VALUES(?, ?, ?, ?, 0, 0)",
                    (name, note, amount, now),
                )
            if remainder > 0:
                self.db.execute(
                    "INSERT INTO accounts(name, note, opening_cents, created_at, archived, system) "
                    "VALUES(?, ?, ?, ?, 0, 1)",
                    ("未分配资金", "初始化时没有分配完的余额", remainder, now),
                )
            self.db.set_setting("initial_total_cents", str(total))
            self.db.set_setting("initialized_at", now)
        self.settings.reload()
        self.after_change()

    # ------------------------------------------------------------------
    # 概览
    # ------------------------------------------------------------------
    def totals(self) -> tuple[int, int]:
        rows = self.db.query(
            "SELECT kind, COALESCE(SUM(amount_cents), 0) AS total FROM transactions GROUP BY kind"
        )
        values = {row["kind"]: int(row["total"]) for row in rows}
        return values.get(INCOME, 0), values.get(EXPENSE, 0)

    def total_balance(self) -> int:
        return self.accounts.total_balance()

    def overview(self, month: str | None = None, *, now: datetime | None = None) -> Overview:
        now = now or datetime.now()
        month = month or month_key(now)
        opening = self.reports.opening_balance(month)
        income, expense = self.transactions.month_totals(month)
        total_income, total_expense = self.totals()
        previous = shift_month(month, -1)
        prev_totals = self.transactions.category_totals(previous)
        totals = self.transactions.category_totals(month)
        categories = [
            CategoryStat(
                key=item.key,
                label=item.label,
                color=item.color,
                amount_cents=totals.get(item.key, 0),
                ratio=percent(totals.get(item.key, 0), expense),
                prev_cents=prev_totals.get(item.key, 0),
            )
            for item in self.reports._report_categories(totals, prev_totals)
        ]
        return Overview(
            month=month,
            opening_cents=opening,
            income_cents=income,
            expense_cents=expense,
            net_cents=income - expense,
            closing_cents=opening + income - expense,
            total_balance_cents=self.accounts.total_balance(),
            opening_total_cents=self.accounts.opening_total(),
            cumulative_income_cents=total_income,
            cumulative_expense_cents=total_expense,
            categories=categories,
            recent=self.transactions.recent(8),
            account_balances=self.accounts.balances(),
            transaction_count=self.transactions.count(month=month),
        )

    # ------------------------------------------------------------------
    # 月报
    # ------------------------------------------------------------------
    def report(self, month: str, *, now: datetime | None = None) -> MonthReport:
        return self.reports.report(month, now=now)

    def month_cards(self, *, now: datetime | None = None) -> list[MonthCard]:
        return self.reports.month_cards(now)

    def ensure_monthly_reports(self, *, now: datetime | None = None) -> int:
        written = self.reports.ensure_snapshots(now)
        if written:
            self.settings.reload()
        return written

    def after_change(self) -> None:
        """任何账目/账户变更后调用：刷新设置缓存与月报快照。"""
        self.settings.reload()
        try:
            self.reports.ensure_snapshots()
        except Exception:  # 快照失败不影响账目本身
            import logging

            logging.getLogger("weekly_planner.finance").exception("刷新月报快照失败")

    # ------------------------------------------------------------------
    # 数据导出 / 备份
    # ------------------------------------------------------------------
    def export_csv(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows: list[list[str]] = [
            ["日期", "类型", "金额", "分类", "来源/内容", "资金分区", "备注"]
        ]
        for item in self.transactions.list():
            rows.append(
                [
                    item.occurred_on.isoformat(),
                    item.kind_label,
                    self._plain(item.amount_cents),
                    item.category_label,
                    item.title,
                    item.account_name,
                    item.note,
                ]
            )
        for transfer in self.transfers.list():
            rows.append(
                [
                    transfer.occurred_on.isoformat(),
                    "资金调动",
                    self._plain(transfer.amount_cents),
                    "",
                    f"{transfer.from_name} → {transfer.to_name}",
                    "",
                    transfer.note,
                ]
            )
        with open(target, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
        return target

    def _plain(self, cents: int) -> str:
        from .finance_models import format_money_plain

        return format_money_plain(cents, self.decimals)

    def backup_to(self, path: str | Path) -> Path:
        return self.db.backup_to(path)

    def restore_from(self, path: str | Path) -> None:
        self.db.restore_from(path)
        self.settings.reload()

    def close(self) -> None:
        self.db.close()
