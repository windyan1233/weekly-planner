"""记账模块的设置（货币、负余额开关、初始化记录）。

保存在财务库自己的 settings 表里，与日程库的设置完全分开。
"""

from __future__ import annotations

from .finance_database import FinanceDatabase
from .finance_models import (
    CURRENCIES,
    DEFAULT_CURRENCY,
    currency_decimals,
    currency_symbol,
)


class FinanceSettings:
    def __init__(self, db: FinanceDatabase) -> None:
        self.db = db
        self._cache: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._cache = {
            row["key"]: row["value"] for row in self.db.query("SELECT key, value FROM settings")
        }

    # ------------------------------------------------------------------
    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, default)

    def set(self, key: str, value: str) -> None:
        self.db.set_setting(key, value)
        self._cache[key] = value

    # ------------------------------------------------------------------
    @property
    def currency(self) -> str:
        code = self.get("currency", DEFAULT_CURRENCY)
        return code if code in CURRENCIES else DEFAULT_CURRENCY

    def set_currency(self, code: str) -> None:
        if code not in CURRENCIES:
            raise ValueError(f"不支持的货币：{code}")
        self.set("currency", code)

    @property
    def symbol(self) -> str:
        return currency_symbol(self.currency)

    @property
    def decimals(self) -> int:
        return currency_decimals(self.currency)

    @property
    def allow_negative(self) -> bool:
        return self.get("allow_negative", "0") == "1"

    def set_allow_negative(self, enabled: bool) -> None:
        self.set("allow_negative", "1" if enabled else "0")

    @property
    def initialized_at(self) -> str:
        return self.get("initialized_at", "")

    @property
    def initial_total_cents(self) -> int:
        try:
            return int(self.get("initial_total_cents", "0"))
        except ValueError:
            return 0

    def mark_initialized(self, total_cents: int) -> None:
        from datetime import datetime

        self.set("initial_total_cents", str(total_cents))
        self.set("initialized_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
