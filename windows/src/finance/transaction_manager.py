"""收入 / 支出账目的增删改查与统计。

所有写操作都在一个事务里完成；保存前会检查金额、分类、账户与余额，
失败时整个操作回滚，不会留下半条记录。
"""

from __future__ import annotations

from datetime import date, datetime
from .account_manager import AccountManager
from .finance_database import FinanceDatabase
from .finance_models import (
    CATEGORY_KEYS,
    EXPENSE,
    INCOME,
    FinanceError,
    Transaction,
    month_bounds,
)


def parse_day(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise FinanceError("日期格式不正确，请使用 2026-10-19 这样的写法。")


def _row_to_transaction(row) -> Transaction:
    created = row["created_at"]
    updated = row["updated_at"]
    return Transaction(
        id=int(row["id"]),
        kind=row["kind"],
        amount_cents=int(row["amount_cents"]),
        occurred_on=parse_day(row["occurred_on"]),
        title=row["title"],
        category=row["category"] or "",
        account_id=int(row["account_id"]),
        note=row["note"] or "",
        created_at=_parse_dt(created),
        updated_at=_parse_dt(updated),
        account_name=row["account_name"] if "account_name" in row.keys() else "",
    )


def _parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


class TransactionManager:
    def __init__(
        self, db: FinanceDatabase, accounts: AccountManager, settings, categories=None
    ) -> None:
        self.db = db
        self.accounts = accounts
        self.settings = settings
        self.categories = categories

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    @staticmethod
    def normalize_kind(kind: str) -> str:
        if kind not in (INCOME, EXPENSE):
            raise FinanceError("账目类型只能是收入或支出。")
        return kind

    def normalize_category(
        self, kind: str, category: str | None, *, allow_hidden: bool = False
    ) -> str:
        if kind == INCOME:
            return ""
        if self.categories is not None:
            if not category or not self.categories.exists(category):
                raise FinanceError("请选择一个支出分类。")
            if not allow_hidden and self.categories.get(category).hidden:
                raise FinanceError("这个支出分类已经隐藏了，请换一个分类。")
            return category
        if not category or category not in CATEGORY_KEYS:
            raise FinanceError("请选择一个支出分类。")
        return category

    @staticmethod
    def normalize_title(title: str) -> str:
        """来源/支出内容为选填；只限制长度。"""
        clean = (title or "").strip()
        if len(clean) > 60:
            raise FinanceError("说明最多 60 个字。")
        return clean

    @staticmethod
    def normalize_amount(amount_cents: int) -> int:
        try:
            cents = int(amount_cents)
        except (TypeError, ValueError) as exc:
            raise FinanceError("金额格式不正确。") from exc
        if cents <= 0:
            raise FinanceError("金额必须大于 0。")
        if cents > 10**13:
            raise FinanceError("金额太大了。")
        return cents

    def _check_account(self, account_id: int, *, allow_archived: bool = False):
        account = self.accounts.get(account_id)
        if account.archived and not allow_archived:
            raise FinanceError(f"资金分区「{account.name}」已归档，不能再记账。")
        return account

    def _ensure_funds(self, account_id: int, delta_cents: int) -> None:
        """delta_cents 为这笔操作对账户余额的影响（支出为负）。"""
        if delta_cents >= 0 or self.settings.allow_negative:
            return
        account = self.accounts.get(account_id)
        balance = self.accounts.balance(account_id)
        if balance + delta_cents < 0:
            raise FinanceError(
                f"资金分区「{account.name}」余额不足："
                f"当前 {self._money(balance)}，这笔需要 {self._money(-delta_cents)}。\n"
                "可以换一个分区、先记一笔收入，或在财务设置里允许负余额。"
            )

    def _money(self, cents: int) -> str:
        from .finance_models import format_money

        return format_money(cents, self.settings.symbol, self.settings.decimals)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def add(
        self,
        kind: str,
        amount_cents: int,
        occurred_on: date | datetime | str,
        title: str,
        category: str | None,
        account_id: int,
        note: str = "",
    ) -> int:
        kind = self.normalize_kind(kind)
        amount = self.normalize_amount(amount_cents)
        day = parse_day(occurred_on)
        title = self.normalize_title(title)
        category = self.normalize_category(kind, category)
        account = self._check_account(account_id)
        delta = amount if kind == INCOME else -amount
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction():
            self._ensure_funds(account.id, delta)
            new_id = self.db.execute(
                "INSERT INTO transactions(kind, amount_cents, occurred_on, title, category, "
                "account_id, note, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    kind,
                    amount,
                    day.isoformat(),
                    title,
                    category,
                    account.id,
                    (note or "").strip(),
                    now,
                    now,
                ),
            )
        return new_id

    def update(
        self,
        transaction_id: int,
        *,
        kind: str | None = None,
        amount_cents: int | None = None,
        occurred_on: date | datetime | str | None = None,
        title: str | None = None,
        category: str | None = None,
        account_id: int | None = None,
        note: str | None = None,
    ) -> None:
        old = self.get(transaction_id)
        new_kind = self.normalize_kind(kind if kind is not None else old.kind)
        new_amount = (
            self.normalize_amount(amount_cents)
            if amount_cents is not None
            else old.amount_cents
        )
        new_day = parse_day(occurred_on) if occurred_on is not None else old.occurred_on
        new_title = self.normalize_title(title if title is not None else old.title)
        new_category = self.normalize_category(
            new_kind,
            category if category is not None else old.category,
            allow_hidden=True,
        )
        new_note = (note if note is not None else old.note).strip()
        new_account_id = int(account_id) if account_id is not None else old.account_id
        if new_account_id == old.account_id:
            account = self._check_account(new_account_id, allow_archived=True)
        else:
            account = self._check_account(new_account_id)

        old_delta = old.amount_cents if old.kind == INCOME else -old.amount_cents
        new_delta = new_amount if new_kind == INCOME else -new_amount
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction():
            if new_account_id == old.account_id:
                self._ensure_funds(new_account_id, new_delta - old_delta)
            else:
                self._ensure_funds(new_account_id, new_delta)
            self.db.execute(
                "UPDATE transactions SET kind = ?, amount_cents = ?, occurred_on = ?, "
                "title = ?, category = ?, account_id = ?, note = ?, updated_at = ? WHERE id = ?",
                (
                    new_kind,
                    new_amount,
                    new_day.isoformat(),
                    new_title,
                    new_category,
                    account.id,
                    new_note,
                    now,
                    transaction_id,
                ),
            )

    def delete(self, transaction_id: int) -> None:
        self.get(transaction_id)
        with self.db.transaction():
            self.db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get(self, transaction_id: int) -> Transaction:
        row = self.db.query_one(
            "SELECT t.*, a.name AS account_name FROM transactions t "
            "JOIN accounts a ON a.id = t.account_id WHERE t.id = ?",
            (transaction_id,),
        )
        if row is None:
            raise FinanceError("这条账目不存在，可能已被删除。")
        return _row_to_transaction(row)

    def list(
        self,
        *,
        month: str | None = None,
        kind: str | None = None,
        category: str | None = None,
        account_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Transaction]:
        clauses: list[str] = []
        params: list = []
        if month:
            start, end = month_bounds(month)
            clauses.append("t.occurred_on >= ? AND t.occurred_on < ?")
            params.extend([start.isoformat(), end.isoformat()])
        if kind:
            clauses.append("t.kind = ?")
            params.append(self.normalize_kind(kind))
        if category:
            clauses.append("t.category = ?")
            params.append(category)
        if account_id:
            clauses.append("t.account_id = ?")
            params.append(int(account_id))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT t.*, a.name AS account_name FROM transactions t "
            "JOIN accounts a ON a.id = t.account_id"
            + where
            + " ORDER BY t.occurred_on DESC, t.id DESC"
        )
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
        return [_row_to_transaction(row) for row in self.db.query(sql, params)]

    def count(
        self,
        *,
        month: str | None = None,
        kind: str | None = None,
        category: str | None = None,
        account_id: int | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list = []
        if month:
            start, end = month_bounds(month)
            clauses.append("occurred_on >= ? AND occurred_on < ?")
            params.extend([start.isoformat(), end.isoformat()])
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if account_id:
            clauses.append("account_id = ?")
            params.append(int(account_id))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return int(self.db.scalar(f"SELECT COUNT(*) FROM transactions{where}", params) or 0)

    def month_totals(self, month: str) -> tuple[int, int]:
        start, end = month_bounds(month)
        rows = self.db.query(
            "SELECT kind, COALESCE(SUM(amount_cents), 0) AS total FROM transactions "
            "WHERE occurred_on >= ? AND occurred_on < ? GROUP BY kind",
            (start.isoformat(), end.isoformat()),
        )
        totals = {row["kind"]: int(row["total"]) for row in rows}
        return totals.get(INCOME, 0), totals.get(EXPENSE, 0)

    def net_before(self, month: str) -> int:
        start, _ = month_bounds(month)
        row = self.db.query_one(
            "SELECT COALESCE(SUM(CASE kind WHEN 'income' THEN amount_cents "
            "ELSE -amount_cents END), 0) AS net FROM transactions WHERE occurred_on < ?",
            (start.isoformat(),),
        )
        return int(row["net"] or 0) if row else 0

    def category_totals(self, month: str) -> dict[str, int]:
        start, end = month_bounds(month)
        rows = self.db.query(
            "SELECT category, COALESCE(SUM(amount_cents), 0) AS total FROM transactions "
            "WHERE kind = 'expense' AND occurred_on >= ? AND occurred_on < ? "
            "GROUP BY category",
            (start.isoformat(), end.isoformat()),
        )
        return {row["category"]: int(row["total"]) for row in rows}

    def category_transactions(self, month: str, category: str) -> list[Transaction]:
        return self.list(month=month, category=category, kind=EXPENSE)

    def recent(self, limit: int = 8) -> list[Transaction]:
        return self.list(limit=limit)

    def months(self) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT substr(occurred_on, 1, 7) AS month FROM transactions "
            "UNION SELECT DISTINCT substr(occurred_on, 1, 7) FROM transfers ORDER BY month"
        )
        return [row["month"] for row in rows]

    def first_month(self) -> str | None:
        months = self.months()
        return months[0] if months else None
