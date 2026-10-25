"""记账模块测试：余额、分类、资金分区、月报结转、数据隔离与界面交互。"""

from __future__ import annotations

import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from tests.support import ROOT, qapp

import unittest

from src.finance import FinanceService
from src.finance.finance_models import (
    EXPENSE,
    INCOME,
    FinanceError,
    MoneyError,
    format_money,
    month_key,
    parse_money,
)

NOW = datetime(2026, 10, 19, 20, 0, 0)
DAY = date(2026, 10, 19)


def yuan(value: str) -> int:
    return parse_money(value)


class FinanceEnv:
    def __init__(self, name: str = "finance") -> None:
        base = ROOT / ".testdata" / "cases"
        base.mkdir(parents=True, exist_ok=True)
        self.dir = base / f"{name}_{uuid.uuid4().hex[:8]}"
        self.dir.mkdir(parents=True, exist_ok=False)
        self.db_path = self.dir / "finance.db"
        self.service = FinanceService(self.db_path)

    def init(self, total: int = 100000) -> None:
        self.service.initialize(
            total,
            [("日常", 60000, ""), ("游戏", 30000, ""), ("应急", 10000, "")],
        )

    def account_id(self, name: str) -> int:
        account = self.service.accounts.find_by_name(name)
        assert account is not None, name
        return account.id

    def add_expense(self, amount: int, *, day=DAY, category="food", account="日常", title="午饭") -> int:
        return self.service.transactions.add(
            EXPENSE, amount, day, title, category, self.account_id(account)
        )

    def add_income(self, amount: int, *, day=DAY, account="日常", title="生活费") -> int:
        return self.service.transactions.add(INCOME, amount, day, title, None, self.account_id(account))

    def close(self) -> None:
        try:
            self.service.close()
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)


class FinanceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.env = FinanceEnv(self.__class__.__name__)

    def tearDown(self) -> None:
        self.env.close()


# ==========================================================================
# 金额与初始化
# ==========================================================================
class MoneyToolsTest(unittest.TestCase):
    def test_parse_money(self) -> None:
        self.assertEqual(parse_money("12.34"), 1234)
        self.assertEqual(parse_money("12.3"), 1230)
        self.assertEqual(parse_money("¥1,234.56"), 123456)
        self.assertEqual(parse_money("0.01"), 1)
        self.assertEqual(parse_money("12.345"), 1235)  # 四舍五入到分
        for bad in ("0", "-1", "", "abc", "1e3"):
            with self.assertRaises(MoneyError):
                parse_money(bad)

    def test_format_money(self) -> None:
        self.assertEqual(format_money(123456), "¥1,234.56")
        self.assertEqual(format_money(-500), "-¥5.00")
        self.assertEqual(format_money(0), "¥0.00")
        self.assertEqual(format_money(1234, "$", 2), "$12.34")
        self.assertEqual(format_money(1234, "¥", 0), "¥1,234")

    def test_month_helpers(self) -> None:
        self.assertEqual(month_key(date(2026, 10, 19)), "2026-10")
        from src.finance.finance_models import shift_month

        self.assertEqual(shift_month("2026-01", -1), "2025-12")
        self.assertEqual(shift_month("2026-12", 1), "2027-01")


class InitializeTest(FinanceTestBase):
    def test_initialize_allocation_and_total(self) -> None:
        self.env.init(100000)
        service = self.env.service
        self.assertTrue(service.is_initialized())
        self.assertEqual(service.total_balance(), 100000)
        self.assertEqual(service.accounts.opening_total(), 100000)
        self.assertEqual(service.settings.initial_total_cents, 100000)
        names = [balance.name for balance in service.accounts.balances()]
        self.assertEqual(names, ["日常", "游戏", "应急"])

    def test_unallocated_remainder(self) -> None:
        self.env.service.initialize(500000, [("日常", 150000, ""), ("游戏", 50000, "")])
        unallocated = self.env.service.accounts.unallocated()
        self.assertIsNotNone(unallocated)
        self.assertEqual(unallocated.opening_cents, 300000)
        self.assertEqual(self.env.service.total_balance(), 500000)

    def test_reject_overallocation_and_duplicate_names(self) -> None:
        with self.assertRaises(FinanceError):
            self.env.service.initialize(1000, [("日常", 1500, "")])
        with self.assertRaises(FinanceError):
            self.env.service.initialize(1000, [("日常", 100, ""), ("日常", 200, "")])
        with self.assertRaises(FinanceError):
            self.env.service.initialize(0, [("日常", 0, "")])
        with self.assertRaises(FinanceError):
            self.env.service.initialize(1000, [])
        # 失败后没有留下半个账户
        self.assertEqual(self.env.service.accounts.count(), 0)

    def test_initialize_twice_rejected(self) -> None:
        self.env.init()
        with self.assertRaises(FinanceError):
            self.env.service.initialize(1000, [("其它", 1000, "")])


# ==========================================================================
# 收入 / 支出
# ==========================================================================
class TransactionTest(FinanceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.env.init(100000)

    def test_income_and_expense_update_balances(self) -> None:
        service = self.env.service
        self.env.add_income(20000)
        self.assertEqual(service.total_balance(), 120000)
        self.env.add_expense(3500)
        self.assertEqual(service.total_balance(), 116500)
        daily = self.env.account_id("日常")
        self.assertEqual(service.accounts.balance(daily), 60000 + 20000 - 3500)
        overview = service.overview("2026-10", now=NOW)
        self.assertEqual(overview.income_cents, 20000)
        self.assertEqual(overview.expense_cents, 3500)
        self.assertEqual(overview.net_cents, 16500)
        self.assertEqual(overview.total_balance_cents, 116500)
        self.assertEqual(overview.opening_cents, 100000)
        self.assertEqual(overview.closing_cents, 116500)

    def test_edit_and_delete_transaction(self) -> None:
        service = self.env.service
        transaction_id = self.env.add_expense(3500)
        self.assertEqual(service.total_balance(), 96500)
        service.transactions.update(transaction_id, amount_cents=5000)
        self.assertEqual(service.total_balance(), 95000)
        service.transactions.update(transaction_id, kind=INCOME, category=None, amount_cents=1000)
        self.assertEqual(service.total_balance(), 101000)
        service.transactions.delete(transaction_id)
        self.assertEqual(service.total_balance(), 100000)

    def test_amount_validation(self) -> None:
        service = self.env.service
        account = self.env.account_id("日常")
        for bad in (0, -100):
            with self.assertRaises(FinanceError):
                service.transactions.add(EXPENSE, bad, DAY, "午饭", "food", account)
        with self.assertRaises(FinanceError):
            service.transactions.add(EXPENSE, 100, DAY, "午饭", "unknown", account)
        # 来源/支出内容选填：空说明也能保存
        empty_title_id = service.transactions.add(EXPENSE, 100, DAY, "  ", "food", account)
        self.assertEqual(service.transactions.get(empty_title_id).title, "")
        with self.assertRaises(FinanceError):
            service.transactions.add(INCOME, 100, DAY, "工资", "food", 99999)
        self.assertEqual(service.transactions.count(), 1)  # 只有上面那笔空说明的支出

    def test_past_month_and_history_edit_recalculates(self) -> None:
        service = self.env.service
        august = date(2026, 8, 5)
        september = date(2026, 9, 5)
        old = self.env.add_income(10000, day=august, title="八月收入")
        self.env.add_expense(2000, day=september, category="life", title="九月购物")
        self.env.add_income(5000, day=DAY, title="十月收入")

        august_report = service.report("2026-08", now=NOW)
        self.assertEqual(august_report.opening_cents, 100000)
        self.assertEqual(august_report.income_cents, 10000)
        self.assertEqual(august_report.closing_cents, 110000)

        september_report = service.report("2026-09", now=NOW)
        self.assertEqual(september_report.opening_cents, 110000)
        self.assertEqual(september_report.closing_cents, 108000)

        october_report = service.report("2026-10", now=NOW)
        self.assertEqual(october_report.opening_cents, 108000)
        self.assertEqual(october_report.income_cents, 5000)
        self.assertEqual(october_report.closing_cents, 113000)
        self.assertEqual(service.total_balance(), 113000)

        # 修改八月的旧账目，后续月份自动跟着变
        service.transactions.update(old, amount_cents=40000)
        self.assertEqual(service.report("2026-08", now=NOW).closing_cents, 140000)
        self.assertEqual(service.report("2026-09", now=NOW).opening_cents, 140000)
        self.assertEqual(service.report("2026-09", now=NOW).closing_cents, 138000)
        self.assertEqual(service.report("2026-10", now=NOW).opening_cents, 138000)
        self.assertEqual(service.report("2026-10", now=NOW).closing_cents, 143000)
        self.assertEqual(service.total_balance(), 143000)

    def test_viewing_reports_does_not_change_balance(self) -> None:
        service = self.env.service
        self.env.add_income(10000)
        before = service.total_balance()
        for month in ("2026-01", "2026-02", "2026-09", "2026-10", "2025-12"):
            service.report(month, now=NOW)
            service.month_cards(now=NOW)
        self.assertEqual(service.total_balance(), before)


# ==========================================================================
# 六个分类
# ==========================================================================
class CategoryTest(FinanceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.env.init(200000)

    def test_six_categories_and_totals(self) -> None:
        service = self.env.service
        amounts = {
            "food": 3500,
            "life": 4500,
            "stationery": 2500,
            "game": 6800,
            "merch": 12000,
            "tech": 19900,
        }
        for category, amount in amounts.items():
            self.env.add_expense(amount, category=category, title=category)
        report = service.report("2026-10", now=NOW)
        totals = {stat.key: stat.amount_cents for stat in report.categories}
        self.assertEqual(list(totals.keys()), list(amounts.keys()))
        self.assertEqual(totals, amounts)
        self.assertEqual(report.expense_cents, sum(amounts.values()))
        self.assertEqual(report.category_total_cents, report.expense_cents)
        ratio_sum = sum(stat.ratio for stat in report.categories)
        self.assertAlmostEqual(ratio_sum, 100.0, delta=0.2)
        # 零支出的分类也要出现在列表里，金额为 0
        empty = service.report("2026-09", now=NOW)
        self.assertEqual(len(empty.categories), 6)
        self.assertTrue(all(stat.amount_cents == 0 for stat in empty.categories))
        self.assertTrue(all(stat.ratio == 0.0 for stat in empty.categories))

    def test_zero_expense_month_has_no_division_error(self) -> None:
        service = self.env.service
        report = service.report("2026-07", now=NOW)
        self.assertEqual(report.expense_cents, 0)
        self.assertEqual(report.categories[0].ratio, 0.0)
        self.assertIn("没有", report.summary_text)

    def test_previous_month_delta(self) -> None:
        service = self.env.service
        self.env.add_expense(10000, day=date(2026, 9, 10), category="food", title="九月吃饭")
        self.env.add_expense(15000, day=date(2026, 10, 10), category="food", title="十月吃饭")
        report = service.report("2026-10", now=NOW)
        food = next(stat for stat in report.categories if stat.key == "food")
        self.assertEqual(food.prev_cents, 10000)
        self.assertEqual(food.delta_cents, 5000)
        self.assertEqual(food.delta_ratio, 50.0)

    def test_category_transactions_dialog_data(self) -> None:
        service = self.env.service
        self.env.add_expense(3500, title="午饭", category="food")
        self.env.add_expense(1200, title="奶茶", category="food")
        items = service.transactions.category_transactions("2026-10", "food")
        self.assertEqual([item.title for item in items], ["奶茶", "午饭"])


# ==========================================================================
# 资金分区与资金调动
# ==========================================================================
class AccountTest(FinanceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.env.init(100000)

    def test_transfer_keeps_total_and_stats(self) -> None:
        service = self.env.service
        self.env.add_income(20000)
        before_total = service.total_balance()
        before_income = service.overview("2026-10", now=NOW).income_cents
        daily = self.env.account_id("日常")
        game = self.env.account_id("游戏")
        service.transfers.add(daily, game, 5000, DAY, "补游戏基金")
        self.assertEqual(service.total_balance(), before_total)
        self.assertEqual(service.accounts.balance(daily), 60000 + 20000 - 5000)
        self.assertEqual(service.accounts.balance(game), 30000 + 5000)
        overview = service.overview("2026-10", now=NOW)
        self.assertEqual(overview.income_cents, before_income)
        self.assertEqual(overview.expense_cents, 0)
        self.assertEqual(sum(stat.amount_cents for stat in overview.categories), 0)
        self.assertEqual(len(service.report("2026-10", now=NOW).transfers), 1)

    def test_transfer_validation(self) -> None:
        service = self.env.service
        daily = self.env.account_id("日常")
        game = self.env.account_id("游戏")
        with self.assertRaises(FinanceError):
            service.transfers.add(daily, daily, 100, DAY, "")
        with self.assertRaises(FinanceError):
            service.transfers.add(daily, game, 0, DAY, "")
        with self.assertRaises(FinanceError):
            service.transfers.add(daily, game, 999999, DAY, "")
        service.settings.set_allow_negative(True)
        service.transfers.add(daily, game, 999999, DAY, "")
        self.assertEqual(service.accounts.balance(daily), 60000 - 999999)

    def test_account_sum_equals_total(self) -> None:
        service = self.env.service
        self.env.add_income(10000)
        self.env.add_expense(3500)
        daily = self.env.account_id("日常")
        game = self.env.account_id("游戏")
        service.transfers.add(daily, game, 2000, DAY, "")
        balances = service.accounts.balances()
        self.assertEqual(sum(item.balance_cents for item in balances), service.total_balance())
        for month in ("2026-09", "2026-10"):
            report = service.report(month, now=NOW)
            self.assertEqual(report.account_closing_total, report.closing_cents)
            self.assertEqual(sum(row.closing_cents for row in report.accounts), report.closing_cents)

    def test_expense_insufficient_funds(self) -> None:
        service = self.env.service
        daily = self.env.account_id("日常")
        with self.assertRaises(FinanceError) as ctx:
            service.transactions.add(EXPENSE, 999999, DAY, "大额", "tech", daily)
        self.assertIn("余额不足", str(ctx.exception))
        service.settings.set_allow_negative(True)
        service.transactions.add(EXPENSE, 999999, DAY, "大额", "tech", daily)
        self.assertLess(service.accounts.balance(daily), 0)
        self.assertEqual(service.total_balance(), 100000 - 999999)

    def test_account_lifecycle(self) -> None:
        service = self.env.service
        new_id = service.accounts.create("新分区", note="测试")
        self.assertEqual(service.accounts.balance(new_id), 0)
        service.accounts.update(new_id, name="改名后的分区", note="备注")
        self.assertEqual(service.accounts.get(new_id).name, "改名后的分区")
        with self.assertRaises(FinanceError):
            service.accounts.create("日常")
        service.accounts.set_archived(new_id, True)
        with self.assertRaises(FinanceError):
            service.transactions.add(INCOME, 100, DAY, "收入", None, new_id)
        service.accounts.set_archived(new_id, False)
        service.accounts.delete(new_id)
        self.assertIsNone(service.accounts.find_by_name("改名后的分区"))

    def test_delete_account_with_records_rejected(self) -> None:
        service = self.env.service
        daily = self.env.account_id("日常")
        self.env.add_expense(100)
        with self.assertRaises(FinanceError):
            service.accounts.delete(daily)
        # 余额不为 0 的也不能删
        with self.assertRaises(FinanceError):
            service.accounts.delete(self.env.account_id("游戏"))
        system = service.accounts.ensure_unallocated()
        with self.assertRaises(FinanceError):
            service.accounts.delete(system)
        with self.assertRaises(FinanceError):
            service.accounts.set_archived(system, True)

    def test_monthly_account_rows(self) -> None:
        service = self.env.service
        daily = self.env.account_id("日常")
        game = self.env.account_id("游戏")
        service.transfers.add(daily, game, 5000, DAY, "")
        self.env.add_income(2000, day=DAY)
        self.env.add_expense(500, day=DAY)
        report = service.report("2026-10", now=NOW)
        row = next(item for item in report.accounts if item.account_id == game)
        self.assertEqual(row.opening_cents, 30000)
        self.assertEqual(row.transfer_in_cents, 5000)
        self.assertEqual(row.closing_cents, 35000)


# ==========================================================================
# 月报与快照
# ==========================================================================
class MonthlyReportTest(FinanceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.env.init(100000)

    def test_report_numbers(self) -> None:
        service = self.env.service
        self.env.add_income(30000, day=date(2026, 9, 3))
        self.env.add_expense(5000, day=date(2026, 9, 20), category="life")
        report = service.report("2026-09", now=NOW)
        self.assertEqual(report.month, "2026-09")
        self.assertEqual(report.opening_cents, 100000)
        self.assertEqual(report.income_cents, 30000)
        self.assertEqual(report.expense_cents, 5000)
        self.assertEqual(report.net_cents, 25000)
        self.assertEqual(report.closing_cents, 125000)
        self.assertIn("本月总收入为 ¥300.00", report.summary_text)
        self.assertIn("总支出为 ¥50.00", report.summary_text)
        self.assertIn("本月末剩余 ¥1,250.00", report.summary_text)

    def test_ensure_snapshots_after_missed_month_end(self) -> None:
        service = self.env.service
        self.env.add_income(10000, day=date(2026, 8, 1))
        self.env.add_expense(2000, day=date(2026, 9, 1), category="game")
        written = service.ensure_monthly_reports(now=NOW)
        self.assertGreaterEqual(written, 3)
        months = {row["month"] for row in service.db.query("SELECT month FROM monthly_reports")}
        self.assertTrue({"2026-08", "2026-09", "2026-10"} <= months)
        # 快照值与实时计算一致
        for month in ("2026-08", "2026-09", "2026-10"):
            report = service.report(month, now=NOW)
            snapshot = service.db.query_one(
                "SELECT * FROM monthly_reports WHERE month = ?", (month,)
            )
            self.assertEqual(int(snapshot["closing_cents"]), report.closing_cents)
            self.assertEqual(int(snapshot["income_cents"]), report.income_cents)

    def test_snapshot_refresh_after_backdated_edit(self) -> None:
        service = self.env.service
        first = self.env.add_income(10000, day=date(2026, 8, 10))
        service.ensure_monthly_reports(now=NOW)
        before = service.db.query_one(
            "SELECT closing_cents FROM monthly_reports WHERE month = '2026-09'"
        )
        self.assertEqual(int(before["closing_cents"]), 110000)
        service.transactions.update(first, amount_cents=50000)
        service.after_change()
        after = service.db.query_one(
            "SELECT closing_cents FROM monthly_reports WHERE month = '2026-09'"
        )
        self.assertEqual(int(after["closing_cents"]), 150000)
        self.assertEqual(service.total_balance(), 150000)

    def test_month_cards(self) -> None:
        service = self.env.service
        self.env.add_income(10000, day=date(2026, 9, 1))
        cards = service.month_cards(now=NOW)
        self.assertEqual([card.month for card in cards][:2], ["2026-10", "2026-09"])
        september = next(card for card in cards if card.month == "2026-09")
        self.assertEqual(september.income_cents, 10000)
        self.assertEqual(september.closing_cents, 110000)
        self.assertTrue(cards[0].is_current)


# ==========================================================================
# 持久化、备份、隔离
# ==========================================================================
class PersistenceAndIsolationTest(FinanceTestBase):
    def test_persistence_across_reopen(self) -> None:
        self.env.init(100000)
        self.env.add_expense(3500)
        path = self.env.db_path
        self.env.service.close()
        reopened = FinanceService(path)
        try:
            self.assertEqual(reopened.total_balance(), 96500)
            self.assertEqual(reopened.transactions.count(), 1)
            self.assertTrue(reopened.is_initialized())
        finally:
            reopened.close()

    def test_backup_and_restore(self) -> None:
        service = self.env.service
        self.env.init(100000)
        self.env.add_income(20000)
        backup = self.env.dir / "backup.db"
        service.backup_to(backup)
        service.transactions.add(EXPENSE, 3000, DAY, "之后的支出", "food", self.env.account_id("日常"))
        self.assertEqual(service.total_balance(), 117000)
        service.restore_from(backup)
        self.assertEqual(service.total_balance(), 120000)
        self.assertEqual(service.transactions.count(), 1)
        with self.assertRaises(Exception):
            FinanceService.validate_backup(self.env.dir / "missing.db")
        bad = self.env.dir / "bad.db"
        bad.write_text("not a database", encoding="utf-8")
        with self.assertRaises(Exception):
            FinanceService.validate_backup(bad)

    def test_csv_export(self) -> None:
        self.env.init(100000)
        self.env.add_income(20000, title="生活费")
        self.env.add_expense(3500, title="午饭", category="food")
        path = self.env.dir / "export.csv"
        self.env.service.export_csv(path)
        text = path.read_text(encoding="utf-8-sig")
        self.assertIn("日期,类型,金额,分类,来源/内容,资金分区,备注", text)
        self.assertIn("收入", text)
        self.assertIn("午饭", text)
        self.assertIn("200.00", text)

    def test_currency_setting(self) -> None:
        service = self.env.service
        self.env.init(100000)
        self.assertEqual(service.money(123456), "¥1,234.56")
        service.settings.set_currency("USD")
        service.settings.reload()
        self.assertEqual(service.money(123456), "$1,234.56")
        with self.assertRaises(ValueError):
            service.settings.set_currency("XXX")

    def test_finance_db_does_not_touch_schedule_db(self) -> None:
        from src.database import Database
        from src.models import TaskDraft
        from src.settings_store import SettingsStore
        from src.task_manager import PlannerService

        schedule_path = self.env.dir / "planner.db"
        db = Database(schedule_path)
        try:
            settings = SettingsStore(db)
            planner = PlannerService(db, settings)
            task = planner.create_task(
                TaskDraft(title="日程任务", due_at=datetime(2026, 10, 20, 18, 0))
            )
            settings.set("theme", "dark")
            table_count_before = db.scalar(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
            )
        finally:
            db.close()

        # 新建一个财务库（模拟首次启用记账），触发日程库的一次性备份
        FinanceService(self.env.dir / 'finance2.db', schedule_db_path=schedule_path).close()

        db = Database(schedule_path)
        try:
            self.assertEqual(int(db.scalar("SELECT COUNT(*) FROM tasks") or 0), 1)
            self.assertEqual(db.query_one("SELECT title FROM tasks WHERE id = ?", (task.id,))["title"], "日程任务")
            self.assertEqual(SettingsStore(db).get_str("theme"), "dark")
            self.assertEqual(
                int(db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'") or 0),
                int(table_count_before),
            )
            # 首次启用记账时，日程库有一次只读备份
            backups = list(self.env.dir.glob("planner.before-finance-*.db"))
            self.assertEqual(len(backups), 1)
        finally:
            db.close()


# ==========================================================================
# 支出分类（自定义分类版）
# ==========================================================================
class CategoryEditingTest(FinanceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.env.init(100000)

    def test_defaults_seeded(self) -> None:
        repo = self.env.service.categories
        self.assertEqual(
            [item.label for item in repo.list()],
            ["吃饭", "生活", "文具", "游戏", "周边", "科技"],
        )
        self.assertEqual(len(repo.active()), 6)

    def test_add_rename_and_report(self) -> None:
        service = self.env.service
        repo = service.categories
        key = repo.add("宠物")
        self.assertTrue(repo.exists(key))
        account = self.env.account_id("日常")
        transaction_id = service.transactions.add(EXPENSE, 500, DAY, "猫粮", key, account)
        report = service.report("2026-10", now=NOW)
        pet = next(item for item in report.categories if item.key == key)
        self.assertEqual(pet.label, "宠物")
        self.assertEqual(pet.amount_cents, 500)
        self.assertEqual(report.category_total_cents, report.expense_cents)
        repo.rename(key, "宠物用品")
        self.assertEqual(service.transactions.get(transaction_id).category_label, "宠物用品")
        self.assertEqual(repo.get(key).label, "宠物用品")

    def test_duplicate_and_invalid_labels(self) -> None:
        repo = self.env.service.categories
        with self.assertRaises(FinanceError):
            repo.add("吃饭")
        with self.assertRaises(FinanceError):
            repo.add("   ")
        with self.assertRaises(FinanceError):
            repo.add("这是一个特别特别长的分类名字")
        key = repo.add("宠物")
        with self.assertRaises(FinanceError):
            repo.rename(key, "吃饭")

    def test_hidden_category_keeps_history(self) -> None:
        service = self.env.service
        repo = service.categories
        key = repo.add("宠物")
        account = self.env.account_id("日常")
        service.transactions.add(EXPENSE, 500, DAY, "猫粮", key, account)
        repo.set_hidden(key, True)
        self.assertNotIn(key, [item.key for item in repo.active()])
        with self.assertRaises(FinanceError):
            service.transactions.add(EXPENSE, 100, DAY, "猫砂", key, account)
        # 历史月报仍然统计这个隐藏分类，合计不变
        report = service.report("2026-10", now=NOW)
        self.assertIn(key, [item.key for item in report.categories])
        self.assertEqual(report.category_total_cents, report.expense_cents)
        # 修改旧账目时允许保留隐藏分类
        old = service.transactions.list(month="2026-10")[0]
        service.transactions.update(old.id, note="改备注")
        self.assertEqual(service.transactions.get(old.id).category, key)

    def test_keep_at_least_one_active(self) -> None:
        repo = self.env.service.categories
        for item in repo.list()[:5]:
            repo.set_hidden(item.key, True)
        with self.assertRaises(FinanceError):
            repo.set_hidden(repo.active()[0].key, True)
        self.assertEqual(len(repo.active()), 1)

    def test_old_database_migrates(self) -> None:
        # 版本 1 的财务库升级后会自动补上 categories 表与六个默认分类
        import sqlite3

        from src.finance import FinanceService

        old_path = self.env.dir / "old_finance.db"
        seed = FinanceService(old_path)
        seed.close()
        connection = sqlite3.connect(old_path)
        try:
            connection.execute("DROP TABLE categories")
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
        finally:
            connection.close()
        service = FinanceService(old_path)
        try:
            self.assertEqual(len(service.categories.list()), 6)
            self.assertEqual(int(service.db.scalar("PRAGMA user_version")), 2)
        finally:
            service.close()

    def test_fixed_edition_flag_default(self) -> None:
        from src import edition

        # 源码仓库默认是「原版」：界面不显示分类编辑入口
        self.assertFalse(edition.EDITABLE_CATEGORIES)


# ==========================================================================
# 界面
# ==========================================================================
class FinanceUITest(FinanceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.app = qapp()
        from src.database import Database
        from src.theme import ThemeManager

        self.schedule_db = Database(self.env.dir / "planner.db")
        from src.reminder_scheduler import ReminderEngine
        from src.settings_store import SettingsStore
        from src.task_manager import PlannerService

        settings = SettingsStore(self.schedule_db)
        self.planner = PlannerService(self.schedule_db, settings)
        self.engine = ReminderEngine(self.schedule_db, settings)
        self.planner.attach_engine(self.engine)
        self.theme_manager = ThemeManager(self.app)
        self.theme_manager.apply("light")

    def tearDown(self) -> None:
        self.schedule_db.close()
        super().tearDown()

    def _window(self, service=None):
        from src.main_window import MainWindow

        window = MainWindow(
            self.planner,
            self.theme_manager,
            scheduler=None,
            finance_service=service,
        )
        window.show()
        self.app.processEvents()
        return window

    def test_main_window_has_finance_pages(self) -> None:
        self.env.init(100000)
        self.env.add_income(20000)
        self.env.service.after_change()
        window = self._window(self.env.service)
        try:
            self.assertEqual(window._pages.count(), 4)
            window._set_page("overview")
            self.app.processEvents()
            self.assertEqual(window._pages.currentIndex(), 1)
            window._set_page("report")
            self.app.processEvents()
            self.assertEqual(window._pages.currentIndex(), 2)
            window._set_page("accounts")
            self.app.processEvents()
            self.assertEqual(window._pages.currentIndex(), 3)
            window._set_page("schedule")
            self.app.processEvents()
            self.assertEqual(window._pages.currentIndex(), 0)
            self.assertTrue(window.week_view.isVisible())
        finally:
            window.close()

    def test_overview_shows_balance(self) -> None:
        self.env.init(100000)
        self.env.add_expense(3500)
        self.env.service.after_change()
        window = self._window(self.env.service)
        try:
            page = window.finance_ui.overview
            page.refresh()
            self.assertEqual(page.balance_label.text(), "¥965.00")
            self.assertEqual(page.category_total.text(), "¥35.00")
            self.assertEqual(page.recent_box.count(), 1)
        finally:
            window.close()

    def test_transaction_dialog_save_and_validation(self) -> None:
        self.env.init(100000)
        from src.finance.finance_dialogs import TransactionDialog

        dialog = TransactionDialog(self.env.service, kind=EXPENSE)
        dialog.amount_edit.setText("35.00")
        dialog.title_edit.setText("午饭")
        dialog._select_category("food")
        dialog._on_primary()
        self.assertEqual(self.env.service.total_balance(), 96500)
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        dialog.deleteLater()

        bad = TransactionDialog(self.env.service, kind=EXPENSE)
        bad.amount_edit.setText("0")
        bad.title_edit.setText("零元")
        bad._on_primary()
        self.assertTrue(bad.error_label.text())
        self.assertNotEqual(bad.result(), bad.DialogCode.Accepted)
        self.assertEqual(self.env.service.transactions.count(), 1)
        bad.deleteLater()

    def test_transfer_dialog_rejects_same_account(self) -> None:
        self.env.init(100000)
        from src.finance.finance_dialogs import TransferDialog

        dialog = TransferDialog(self.env.service)
        dialog.from_combo.setCurrentIndex(0)
        dialog.to_combo.setCurrentIndex(0)
        dialog.amount_edit.setText("100")
        dialog._on_primary()
        self.assertTrue(dialog.error_label.text())
        self.assertEqual(len(self.env.service.transfers.list()), 0)
        dialog.deleteLater()

    def test_finance_unavailable_still_shows_schedule(self) -> None:
        window = self._window(None)
        try:
            window._set_page("overview")
            self.app.processEvents()
            self.assertEqual(window._pages.currentIndex(), 1)
            window._set_page("schedule")
            self.app.processEvents()
            self.assertEqual(window._pages.currentIndex(), 0)
        finally:
            window.close()

    def test_initial_setup_dialog(self) -> None:
        from src.finance.finance_dialogs import InitialSetupDialog

        dialog = InitialSetupDialog(self.env.service)
        dialog.total_edit.setText("5000")
        dialog._on_primary()
        self.assertTrue(self.env.service.is_initialized())
        self.assertEqual(self.env.service.total_balance(), 500000)
        dialog.deleteLater()

    def test_other_dialogs_construct(self) -> None:
        from src.finance.finance_dialogs import (
            AccountDetailDialog,
            AccountDialog,
            CategoryTransactionsDialog,
            FinanceSettingsDialog,
            TransferDialog,
        )

        self.env.init(100000)
        self.env.add_expense(3500, category="food")
        account_id = self.env.account_id("日常")
        dialogs = [
            AccountDialog(self.env.service),
            AccountDialog(self.env.service, account=self.env.service.accounts.get(account_id)),
            TransferDialog(self.env.service),
            CategoryTransactionsDialog(self.env.service, "2026-10", "food"),
            AccountDetailDialog(self.env.service, account_id),
            FinanceSettingsDialog(self.env.service),
        ]
        for dialog in dialogs:
            self.assertIsNotNone(dialog.windowTitle())
            dialog.deleteLater()

    def test_report_page_month_switch(self) -> None:
        self.env.init(100000)
        self.env.add_income(10000, day=date(2026, 9, 5))
        self.env.add_expense(2000, day=date(2026, 10, 5))
        self.env.service.after_change()
        window = self._window(self.env.service)
        try:
            page = window.finance_ui.report
            page._set_month("2026-09")
            self.app.processEvents()
            self.assertEqual(page.month(), "2026-09")
            self.assertEqual(page.year_combo.currentData(), 2026)
            self.assertEqual(page.month_combo.currentData(), 9)
            page._set_month("2026-10")
            self.app.processEvents()
            self.assertEqual(page.month_combo.currentData(), 10)
        finally:
            window.close()

    def test_month_rollover_generates_reports(self) -> None:
        self.env.init(100000)
        self.env.add_income(10000, day=date(2026, 9, 10))
        window = self._window(self.env.service)
        try:
            window.finance_ui.on_date_changed(datetime(2026, 11, 1, 0, 1))
            self.app.processEvents()
            months = {
                row['month']
                for row in self.env.service.db.query('SELECT month FROM monthly_reports')
            }
            self.assertIn('2026-09', months)
            self.assertIn('2026-10', months)
            self.assertIn('2026-11', months)
        finally:
            window.close()

    def test_palette_switch_keeps_finance_pages_working(self) -> None:
        self.env.init(100000)
        self.env.add_expense(3500)
        self.env.service.after_change()
        window = self._window(self.env.service)
        try:
            window._set_page("overview")
            self.app.processEvents()
            window.toggle_theme()
            self.app.processEvents()
            for key in ("overview", "report", "accounts"):
                window._set_page(key)
                self.app.processEvents()
                self.assertGreaterEqual(window._pages.currentIndex(), 1)
            window.toggle_theme()
            self.app.processEvents()
        finally:
            window.force_close()


if __name__ == "__main__":
    unittest.main()
