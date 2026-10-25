"""记账模块的数据模型与金额工具。

金额一律用「最小货币单位的整数」保存（人民币 = 分），只在解析/显示时用
:class:`decimal.Decimal`，避免二进制浮点误差。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# --------------------------------------------------------------------------
# 六个固定支出分类（第一版不增加其它分类）
# --------------------------------------------------------------------------
CATEGORIES: tuple[tuple[str, str, str, str], ...] = (
    ("food", "吃饭", "#E08A5C", "早餐、午餐、晚餐、零食、饮料、外卖"),
    ("life", "生活", "#5B8DEF", "日用品、洗漱、交通、个人生活开销"),
    ("stationery", "文具", "#9B87E8", "书籍、笔、本子、学习与办公用品"),
    ("game", "游戏", "#57AE84", "游戏购买、充值、DLC、会员"),
    ("merch", "周边", "#DD7BA6", "动漫周边、手办、徽章、立牌"),
    ("tech", "科技", "#6A7BDB", "电子设备、数码配件、电脑配件与服务"),
)
CATEGORY_KEYS: tuple[str, ...] = tuple(item[0] for item in CATEGORIES)
CATEGORY_LABELS: dict[str, str] = {item[0]: item[1] for item in CATEGORIES}
CATEGORY_COLORS: dict[str, str] = {item[0]: item[2] for item in CATEGORIES}
CATEGORY_NOTES: dict[str, str] = {item[0]: item[3] for item in CATEGORIES}

# 新增自定义分类时轮换使用的柔和色
CUSTOM_CATEGORY_COLORS: tuple[str, ...] = (
    "#E08A5C",
    "#5B8DEF",
    "#9B87E8",
    "#57AE84",
    "#DD7BA6",
    "#6A7BDB",
    "#D9A441",
    "#5FA8A0",
    "#C97F6B",
    "#8C8FE0",
)

# 运行时的分类名称表：自定义分类改名后，历史账目显示新名字
_RUNTIME_LABELS: dict[str, str] = dict(CATEGORY_LABELS)


def set_category_labels(labels: dict[str, str]) -> None:
    global _RUNTIME_LABELS
    _RUNTIME_LABELS = dict(labels)


def category_label(key: str) -> str:
    return _RUNTIME_LABELS.get(key, key)


@dataclass
class Category:
    key: str
    label: str
    color: str
    sort_order: int = 0
    hidden: bool = False


INCOME = "income"
EXPENSE = "expense"
KIND_LABELS = {INCOME: "收入", EXPENSE: "支出"}

# 货币：代码 -> (符号, 小数位, 名称)
CURRENCIES: dict[str, tuple[str, int, str]] = {
    "CNY": ("¥", 2, "人民币"),
    "USD": ("$", 2, "美元"),
    "EUR": ("€", 2, "欧元"),
    "JPY": ("¥", 0, "日元"),
    "GBP": ("£", 2, "英镑"),
}
DEFAULT_CURRENCY = "CNY"

UNALLOCATED_NAME = "未分配资金"


class MoneyError(ValueError):
    """金额格式不合法。"""


class FinanceError(Exception):
    """记账业务规则不允许的操作（余额不足、重名、账户仍有记录等）。"""


# --------------------------------------------------------------------------
# 金额
# --------------------------------------------------------------------------
def currency_symbol(code: str) -> str:
    return CURRENCIES.get(code, CURRENCIES[DEFAULT_CURRENCY])[0]


def category_color(key: str) -> str:
    return CATEGORY_COLORS.get(key, "#8A91A6")


def currency_decimals(code: str) -> int:
    return CURRENCIES.get(code, CURRENCIES[DEFAULT_CURRENCY])[1]


def parse_money(text: str | int | Decimal, decimals: int = 2) -> int:
    """把用户输入（如 ``12.34``）解析成最小单位整数（1234 分）。

    只接受正数；超过精度时按四舍五入处理。
    """
    if isinstance(text, int):
        if text <= 0:
            raise MoneyError("金额必须大于 0。")
        return int(text) * (10**decimals)
    if isinstance(text, Decimal):
        amount = text
    else:
        cleaned = str(text).strip()
        for symbol in ("¥", "￥", "$", "€", "£", ",", "，", " "):
            cleaned = cleaned.replace(symbol, "")
        if not cleaned:
            raise MoneyError("请输入金额。")
        if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
            raise MoneyError("金额格式不正确，请输入数字，例如 12.50。")
        try:
            amount = Decimal(cleaned)
        except (InvalidOperation, ValueError) as exc:
            raise MoneyError("金额格式不正确，请输入数字，例如 12.50。") from exc
    if not amount.is_finite():
        raise MoneyError("金额格式不正确。")
    if amount <= 0:
        raise MoneyError("金额必须大于 0。")
    quantum = Decimal(1).scaleb(-decimals)
    rounded = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    cents = int(rounded.scaleb(decimals))
    if cents <= 0:
        raise MoneyError("金额太小了，至少要是最小货币单位的 1。")
    return cents


def format_money(cents: int, symbol: str = "¥", decimals: int = 2) -> str:
    """把最小单位整数格式化成带千分位的金额字符串。"""
    value = int(cents)
    sign = "-" if value < 0 else ""
    value = abs(value)
    scale = 10**decimals
    whole, frac = divmod(value, scale)
    if decimals > 0:
        text = f"{whole:,}.{frac:0{decimals}d}"
    else:
        text = f"{whole:,}"
    return f"{sign}{symbol}{text}"


def format_money_plain(cents: int, decimals: int = 2) -> str:
    """不带符号的金额（导出 CSV 用）。"""
    value = int(cents)
    scale = 10**decimals
    whole, frac = divmod(abs(value), scale)
    sign = "-" if value < 0 else ""
    if decimals > 0:
        return f"{sign}{whole}.{frac:0{decimals}d}"
    return f"{sign}{whole}"


def percent(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total * 100, 1)


# --------------------------------------------------------------------------
# 月份
# --------------------------------------------------------------------------
def month_key(value: date | datetime | str) -> str:
    if isinstance(value, str):
        return value[:7]
    return value.strftime("%Y-%m")


def parse_month(value: str) -> date:
    year, month = value.split("-")[:2]
    return date(int(year), int(month), 1)


def shift_month(month: str, offset: int) -> str:
    base = parse_month(month)
    total = base.year * 12 + (base.month - 1) + offset
    year, month_index = divmod(total, 12)
    return f"{year:04d}-{month_index + 1:02d}"


def month_display(month: str) -> str:
    base = parse_month(month)
    return f"{base.year} 年 {base.month} 月"


def month_short(month: str) -> str:
    base = parse_month(month)
    return f"{base.month} 月"


def month_bounds(month: str) -> tuple[date, date]:
    start = parse_month(month)
    return start, parse_month(shift_month(month, 1))


def month_of_today(now: datetime | None = None) -> str:
    return month_key(now or datetime.now())


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------
@dataclass
class Account:
    id: int
    name: str
    note: str = ""
    opening_cents: int = 0
    created_at: datetime | None = None
    archived: bool = False
    system: bool = False

    @property
    def created_text(self) -> str:
        return self.created_at.strftime("%Y-%m-%d") if self.created_at else ""


@dataclass
class AccountBalance:
    account: Account
    opening_cents: int
    income_cents: int
    expense_cents: int
    transfer_in_cents: int
    transfer_out_cents: int
    balance_cents: int

    @property
    def name(self) -> str:
        return self.account.name


@dataclass
class Transaction:
    id: int
    kind: str
    amount_cents: int
    occurred_on: date
    title: str
    category: str
    account_id: int
    note: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    account_name: str = ""

    @property
    def signed_cents(self) -> int:
        return self.amount_cents if self.kind == INCOME else -self.amount_cents

    @property
    def category_label(self) -> str:
        if self.kind == INCOME:
            return "收入"
        return category_label(self.category)

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


@dataclass
class Transfer:
    id: int
    from_account_id: int
    to_account_id: int
    amount_cents: int
    occurred_on: date
    note: str = ""
    created_at: datetime | None = None
    from_name: str = ""
    to_name: str = ""


@dataclass
class CategoryStat:
    key: str
    label: str
    color: str
    amount_cents: int
    ratio: float
    prev_cents: int = 0

    @property
    def delta_cents(self) -> int:
        return self.amount_cents - self.prev_cents

    @property
    def delta_ratio(self) -> float | None:
        if self.prev_cents <= 0:
            return None
        return round((self.amount_cents - self.prev_cents) / self.prev_cents * 100, 1)


@dataclass
class AccountMonthRow:
    account_id: int
    name: str
    opening_cents: int
    income_cents: int
    expense_cents: int
    transfer_in_cents: int
    transfer_out_cents: int
    closing_cents: int
    archived: bool = False


@dataclass
class MonthReport:
    month: str
    opening_cents: int
    income_cents: int
    expense_cents: int
    net_cents: int
    closing_cents: int
    categories: list[CategoryStat] = field(default_factory=list)
    accounts: list[AccountMonthRow] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    generated_at: datetime | None = None
    is_current: bool = False
    has_data: bool = False
    summary_text: str = ""

    @property
    def category_total_cents(self) -> int:
        return sum(item.amount_cents for item in self.categories)

    @property
    def top_category(self) -> CategoryStat | None:
        if not self.categories or self.category_total_cents <= 0:
            return None
        return max(self.categories, key=lambda item: item.amount_cents)

    @property
    def account_closing_total(self) -> int:
        return sum(row.closing_cents for row in self.accounts)


@dataclass
class MonthCard:
    month: str
    income_cents: int
    expense_cents: int
    closing_cents: int
    has_data: bool
    is_current: bool = False


@dataclass
class Overview:
    month: str
    opening_cents: int
    income_cents: int
    expense_cents: int
    net_cents: int
    closing_cents: int
    total_balance_cents: int
    opening_total_cents: int
    cumulative_income_cents: int
    cumulative_expense_cents: int
    categories: list[CategoryStat] = field(default_factory=list)
    recent: list[Transaction] = field(default_factory=list)
    account_balances: list[AccountBalance] = field(default_factory=list)
    transaction_count: int = 0
