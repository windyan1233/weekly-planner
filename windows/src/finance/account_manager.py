"""资金分区的创建、重命名、归档与余额计算。

余额不单独存储，而是由「开户金额 + 收入 - 支出 + 转入 - 转出」实时推导，
因此各分区余额之和永远等于全局总余额，也不会因为直接改数字而掩盖资金流动。
"""

from __future__ import annotations

from datetime import datetime
from .finance_database import FinanceDatabase
from .finance_models import (
    Account,
    AccountBalance,
    FinanceError,
    UNALLOCATED_NAME,
)

_BALANCE_EXPR = """
    a.opening_cents
    + COALESCE((SELECT SUM(t.amount_cents) FROM transactions t
                WHERE t.account_id = a.id AND t.kind = 'income'), 0)
    - COALESCE((SELECT SUM(t.amount_cents) FROM transactions t
                WHERE t.account_id = a.id AND t.kind = 'expense'), 0)
    + COALESCE((SELECT SUM(f.amount_cents) FROM transfers f
                WHERE f.to_account_id = a.id), 0)
    - COALESCE((SELECT SUM(f.amount_cents) FROM transfers f
                WHERE f.from_account_id = a.id), 0)
"""


def _parse_created(text: str | None) -> datetime | None:
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _row_to_account(row) -> Account:
    return Account(
        id=int(row["id"]),
        name=row["name"],
        note=row["note"] or "",
        opening_cents=int(row["opening_cents"] or 0),
        created_at=_parse_created(row["created_at"]),
        archived=bool(row["archived"]),
        system=bool(row["system"]),
    )


class AccountManager:
    def __init__(self, db: FinanceDatabase) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get(self, account_id: int) -> Account:
        row = self.db.query_one("SELECT * FROM accounts WHERE id = ?", (account_id,))
        if row is None:
            raise FinanceError("资金分区不存在，可能已被删除。")
        return _row_to_account(row)

    def find_by_name(self, name: str) -> Account | None:
        row = self.db.query_one(
            "SELECT * FROM accounts WHERE name = ? COLLATE NOCASE", (name.strip(),)
        )
        return _row_to_account(row) if row else None

    def list(self, *, include_archived: bool = True) -> list[Account]:
        sql = "SELECT * FROM accounts"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY archived, id"
        return [_row_to_account(row) for row in self.db.query(sql)]

    def balances(self, *, include_archived: bool = True) -> list[AccountBalance]:
        where = "" if include_archived else " WHERE a.archived = 0"
        rows = self.db.query(
            f"""
            SELECT a.*,
                   {_BALANCE_EXPR} AS balance_cents,
                   COALESCE((SELECT SUM(t.amount_cents) FROM transactions t
                             WHERE t.account_id = a.id AND t.kind = 'income'), 0) AS income_cents,
                   COALESCE((SELECT SUM(t.amount_cents) FROM transactions t
                             WHERE t.account_id = a.id AND t.kind = 'expense'), 0) AS expense_cents,
                   COALESCE((SELECT SUM(f.amount_cents) FROM transfers f
                             WHERE f.to_account_id = a.id), 0) AS transfer_in_cents,
                   COALESCE((SELECT SUM(f.amount_cents) FROM transfers f
                             WHERE f.from_account_id = a.id), 0) AS transfer_out_cents
            FROM accounts a{where}
            ORDER BY a.archived, a.id
            """
        )
        result: list[AccountBalance] = []
        for row in rows:
            result.append(
                AccountBalance(
                    account=_row_to_account(row),
                    opening_cents=int(row["opening_cents"] or 0),
                    income_cents=int(row["income_cents"] or 0),
                    expense_cents=int(row["expense_cents"] or 0),
                    transfer_in_cents=int(row["transfer_in_cents"] or 0),
                    transfer_out_cents=int(row["transfer_out_cents"] or 0),
                    balance_cents=int(row["balance_cents"] or 0),
                )
            )
        return result

    def balance(self, account_id: int) -> int:
        row = self.db.query_one(
            f"SELECT {_BALANCE_EXPR} AS balance_cents FROM accounts a WHERE a.id = ?",
            (account_id,),
        )
        if row is None:
            raise FinanceError("资金分区不存在。")
        return int(row["balance_cents"] or 0)

    def total_balance(self) -> int:
        row = self.db.query_one(f"SELECT SUM({_BALANCE_EXPR}) AS total FROM accounts a")
        return int(row["total"] or 0) if row else 0

    def opening_total(self) -> int:
        row = self.db.query_one("SELECT COALESCE(SUM(opening_cents), 0) AS total FROM accounts")
        return int(row["total"] or 0) if row else 0

    def count(self, *, include_archived: bool = True) -> int:
        sql = "SELECT COUNT(*) FROM accounts"
        if not include_archived:
            sql += " WHERE archived = 0"
        return int(self.db.scalar(sql) or 0)

    def unallocated(self) -> Account | None:
        return self.find_by_name(UNALLOCATED_NAME)

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------
    def _check_name(self, name: str, exclude_id: int | None = None) -> str:
        clean = (name or "").strip()
        if not clean:
            raise FinanceError("资金分区名称不能为空。")
        if len(clean) > 30:
            raise FinanceError("资金分区名称最多 30 个字。")
        existing = self.find_by_name(clean)
        if existing is not None and existing.id != exclude_id:
            raise FinanceError(f"已经有一个叫「{clean}」的资金分区了。")
        return clean

    def create(
        self,
        name: str,
        *,
        opening_cents: int = 0,
        note: str = "",
        system: bool = False,
    ) -> int:
        clean = self._check_name(name)
        if opening_cents < 0:
            raise FinanceError("开户金额不能是负数。")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction():
            account_id = self.db.execute(
                "INSERT INTO accounts(name, note, opening_cents, created_at, archived, system) "
                "VALUES(?, ?, ?, ?, 0, ?)",
                (clean, (note or "").strip(), int(opening_cents), now, 1 if system else 0),
            )
        return account_id

    def update(
        self,
        account_id: int,
        *,
        name: str | None = None,
        note: str | None = None,
        opening_cents: int | None = None,
    ) -> None:
        account = self.get(account_id)
        new_name = self._check_name(name, exclude_id=account_id) if name is not None else account.name
        new_note = (note or "").strip() if note is not None else account.note
        new_opening = int(opening_cents) if opening_cents is not None else account.opening_cents
        if new_opening < 0:
            raise FinanceError("开户金额不能是负数。")
        with self.db.transaction():
            self.db.execute(
                "UPDATE accounts SET name = ?, note = ?, opening_cents = ? WHERE id = ?",
                (new_name, new_note, new_opening, account_id),
            )

    def set_archived(self, account_id: int, archived: bool) -> None:
        account = self.get(account_id)
        if account.system and archived:
            raise FinanceError("「未分配资金」是系统分区，不能归档。")
        with self.db.transaction():
            self.db.execute(
                "UPDATE accounts SET archived = ? WHERE id = ?",
                (1 if archived else 0, account_id),
            )

    def delete(self, account_id: int) -> None:
        account = self.get(account_id)
        if account.system:
            raise FinanceError("「未分配资金」是系统分区，不能删除。")
        used = int(self.db.scalar("SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,)) or 0)
        transferred = int(
            self.db.scalar(
                "SELECT COUNT(*) FROM transfers WHERE from_account_id = ? OR to_account_id = ?",
                (account_id, account_id),
            )
            or 0
        )
        if used or transferred:
            raise FinanceError(
                "这个资金分区已经有收支或转账记录，不能直接删除。\n"
                "可以把它归档，历史月报仍会保留它。"
            )
        if self.balance(account_id) != 0:
            raise FinanceError("这个资金分区还有余额，请先用「资金调动」把余额转走。")
        with self.db.transaction():
            self.db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def ensure_unallocated(self, opening_cents: int = 0) -> int:
        account = self.unallocated()
        if account is not None:
            return account.id
        return self.create(UNALLOCATED_NAME, opening_cents=opening_cents, system=True)

    # ------------------------------------------------------------------
    # 账户流水（资金管理页/详情弹窗用）
    # ------------------------------------------------------------------
    def flows(self, account_id: int, limit: int = 200) -> list[dict]:
        rows = self.db.query(
            """
            SELECT 'income' AS flow_kind, id, occurred_on,
                   COALESCE(NULLIF(title, ''), '未填写说明的收入') AS label,
                   amount_cents AS delta, note
            FROM transactions WHERE account_id = ? AND kind = 'income'
            UNION ALL
            SELECT 'expense', id, occurred_on,
                   COALESCE(NULLIF(title, ''), '未填写说明的支出'),
                   -amount_cents, note
            FROM transactions WHERE account_id = ? AND kind = 'expense'
            UNION ALL
            SELECT 'transfer_in', f.id, f.occurred_on,
                   (SELECT name FROM accounts WHERE id = f.from_account_id) || ' → 转入',
                   f.amount_cents, f.note
            FROM transfers f WHERE f.to_account_id = ?
            UNION ALL
            SELECT 'transfer_out', f.id, f.occurred_on,
                   '转出 → ' || (SELECT name FROM accounts WHERE id = f.to_account_id),
                   -f.amount_cents, f.note
            FROM transfers f WHERE f.from_account_id = ?
            ORDER BY occurred_on DESC, id DESC
            LIMIT ?
            """,
            (account_id, account_id, account_id, account_id, limit),
        )
        return [dict(row) for row in rows]
