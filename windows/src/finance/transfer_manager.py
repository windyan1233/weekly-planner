"""资金调动（内部转账）。

转账只改变两个分区的余额，不计入收入/支出，也不影响分类统计。
转出与转入是一条记录，避免被当成一笔支出 + 一笔收入重复计算。
"""

from __future__ import annotations

from datetime import datetime

from .account_manager import AccountManager
from .finance_database import FinanceDatabase
from .finance_models import FinanceError, Transfer, month_bounds
from .transaction_manager import parse_day


def _row_to_transfer(row) -> Transfer:
    return Transfer(
        id=int(row["id"]),
        from_account_id=int(row["from_account_id"]),
        to_account_id=int(row["to_account_id"]),
        amount_cents=int(row["amount_cents"]),
        occurred_on=parse_day(row["occurred_on"]),
        note=row["note"] or "",
        created_at=None,
        from_name=row["from_name"] if "from_name" in row.keys() else "",
        to_name=row["to_name"] if "to_name" in row.keys() else "",
    )


class TransferManager:
    def __init__(self, db: FinanceDatabase, accounts: AccountManager, settings) -> None:
        self.db = db
        self.accounts = accounts
        self.settings = settings

    def add(
        self,
        from_account_id: int,
        to_account_id: int,
        amount_cents: int,
        occurred_on,
        note: str = "",
    ) -> int:
        amount = int(amount_cents)
        if amount <= 0:
            raise FinanceError("调动金额必须大于 0。")
        if int(from_account_id) == int(to_account_id):
            raise FinanceError("转出和转入不能是同一个资金分区。")
        source = self.accounts.get(from_account_id)
        target = self.accounts.get(to_account_id)
        if source.archived or target.archived:
            raise FinanceError("已归档的资金分区不能参与资金调动。")
        day = parse_day(occurred_on)
        balance = self.accounts.balance(source.id)
        if balance < amount and not self.settings.allow_negative:
            raise FinanceError(
                f"「{source.name}」余额不足：当前 {self._money(balance)}，"
                f"无法转出 {self._money(amount)}。"
            )
        with self.db.transaction():
            transfer_id = self.db.execute(
                "INSERT INTO transfers(from_account_id, to_account_id, amount_cents, "
                "occurred_on, note, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (
                    source.id,
                    target.id,
                    amount,
                    day.isoformat(),
                    (note or "").strip(),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        return transfer_id

    def delete(self, transfer_id: int) -> None:
        self.get(transfer_id)
        with self.db.transaction():
            self.db.execute("DELETE FROM transfers WHERE id = ?", (transfer_id,))

    def get(self, transfer_id: int) -> Transfer:
        row = self.db.query_one(
            "SELECT f.*, a.name AS from_name, b.name AS to_name FROM transfers f "
            "JOIN accounts a ON a.id = f.from_account_id "
            "JOIN accounts b ON b.id = f.to_account_id WHERE f.id = ?",
            (transfer_id,),
        )
        if row is None:
            raise FinanceError("这条资金调动记录不存在。")
        return _row_to_transfer(row)

    def list(self, *, month: str | None = None, limit: int | None = None) -> list[Transfer]:
        clauses: list[str] = []
        params: list = []
        if month:
            start, end = month_bounds(month)
            clauses.append("f.occurred_on >= ? AND f.occurred_on < ?")
            params.extend([start.isoformat(), end.isoformat()])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT f.*, a.name AS from_name, b.name AS to_name FROM transfers f "
            "JOIN accounts a ON a.id = f.from_account_id "
            "JOIN accounts b ON b.id = f.to_account_id"
            + where
            + " ORDER BY f.occurred_on DESC, f.id DESC"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [_row_to_transfer(row) for row in self.db.query(sql, params)]

    def _money(self, cents: int) -> str:
        from .finance_models import format_money

        return format_money(cents, self.settings.symbol, self.settings.decimals)
