"""记账页面的装配与交互（控制器 + 页面容器）。

界面层只调用 :class:`FinanceService`；对话框在这里统一打开，成功后再刷新页面。
"""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from . import finance_icons
from .finance_dialogs import (
    AccountDetailDialog,
    AccountDialog,
    CategoryTransactionsDialog,
    FinanceSettingsDialog,
    InitialSetupDialog,
    TransactionDialog,
    TransferDialog,
)
from .finance_models import EXPENSE, FinanceError, month_of_today
from .finance_pages import AccountsPage, OverviewPage, ReportPage
from .finance_widgets import EmptyState

logger = logging.getLogger("weekly_planner.finance.ui")


class FinanceUI(QObject):
    navigate_requested = Signal(str)

    def __init__(self, service, theme_manager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.theme_manager = theme_manager
        self._last_month = month_of_today()
        if service is not None:
            self.overview = OverviewPage(self)
            self.report = ReportPage(self)
            self.accounts = AccountsPage(self)
            self.pages = {
                "overview": self.overview,
                "report": self.report,
                "accounts": self.accounts,
            }
        else:
            self.overview = self.report = self.accounts = None
            self.pages = {}

    # ------------------------------------------------------------------
    @property
    def palette(self):
        return self.theme_manager.palette

    def page(self, key: str) -> QWidget:
        if key in self.pages:
            return self.pages[key]
        return self._error_page()

    def _error_page(self) -> QWidget:
        from PySide6.QtWidgets import QFrame, QVBoxLayout

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 30, 24, 30)
        card_layout.addWidget(
            EmptyState(
                "记账模块暂时不可用",
                "财务数据库打开失败，日程与提醒不受影响。可以查看日志了解原因，"
                "或到「设置 → 数据」恢复备份。",
                icon=finance_icons.finance_icon("wallet", "#D2606B", 40),
            )
        )
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def navigate(self, key: str) -> None:
        self.navigate_requested.emit(key)

    def open_report(self, month: str | None = None) -> None:
        if self.report is not None and month:
            self.report._set_month(month)
        self.navigate_requested.emit('report')

    def dialog_parent(self) -> QWidget | None:
        if self.overview is not None:
            return self.overview.window()
        return None

    # ------------------------------------------------------------------
    # 页面刷新
    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        if self.service is None:
            return
        for page in (self.overview, self.report, self.accounts):
            try:
                page.refresh()
            except Exception:  # noqa: BLE001 - 记账异常不能影响日程
                logger.exception("刷新记账页面失败：%s", type(page).__name__)

    def apply_palette(self, palette) -> None:
        if self.service is None:
            return
        for page in (self.overview, self.report, self.accounts):
            try:
                page.apply_palette(palette)
            except Exception:  # noqa: BLE001
                logger.exception("应用记账主题失败")

    def on_date_changed(self, now: datetime) -> None:
        """跨天时检查月份是否变化：进入新月份就补生成上个月的月报。"""
        current = month_of_today(now)
        if current != self._last_month:
            self._last_month = current
            try:
                self.service.ensure_monthly_reports(now=now)
            except Exception:  # noqa: BLE001 - 月报生成失败不影响记账
                logger.exception("跨月生成月报失败")
            if self.report is not None:
                self.report._set_month(current)
            self.refresh_all()

    # ------------------------------------------------------------------
    # 对话框
    # ------------------------------------------------------------------
    def open_initialize_dialog(self) -> None:
        if self.service is None or self.service.is_initialized():
            return
        dialog = InitialSetupDialog(self.service, parent=self.dialog_parent())
        if dialog.exec():
            self.refresh_all()

    def open_transaction_dialog(self, kind: str = EXPENSE) -> None:
        if self.service is None or not self.service.is_initialized():
            self.open_initialize_dialog()
            return
        dialog = TransactionDialog(self.service, kind=kind, parent=self.dialog_parent())
        if dialog.exec():
            self.refresh_all()

    def open_transaction_by_id(self, transaction_id: int) -> None:
        if self.service is None:
            return
        try:
            transaction = self.service.transactions.get(transaction_id)
        except FinanceError as exc:
            QMessageBox.warning(self.dialog_parent(), "无法打开账目", str(exc))
            return
        dialog = TransactionDialog(self.service, transaction=transaction, parent=self.dialog_parent())
        if dialog.exec():
            self.refresh_all()

    def open_transfer_dialog(self) -> None:
        if self.service is None or not self.service.is_initialized():
            self.open_initialize_dialog()
            return
        dialog = TransferDialog(self.service, parent=self.dialog_parent())
        if dialog.exec():
            self.refresh_all()

    def open_account_dialog(self) -> None:
        if self.service is None:
            return
        if not self.service.is_initialized():
            self.open_initialize_dialog()
            return
        dialog = AccountDialog(self.service, parent=self.dialog_parent())
        if dialog.exec():
            self.refresh_all()

    def open_account_dialog_by_id(self, account_id: int) -> None:
        if self.service is None:
            return
        try:
            account = self.service.accounts.get(account_id)
        except FinanceError as exc:
            QMessageBox.warning(self.dialog_parent(), "无法打开资金分区", str(exc))
            return
        dialog = AccountDialog(self.service, account=account, parent=self.dialog_parent())
        if dialog.exec():
            self.refresh_all()

    def open_account_detail(self, account_id: int) -> None:
        if self.service is None:
            return
        dialog = AccountDetailDialog(self.service, account_id, parent=self.dialog_parent())
        dialog.exec()

    def open_category_dialog(self, month: str, category: str) -> None:
        if self.service is None:
            return
        dialog = CategoryTransactionsDialog(
            self.service, month, category, parent=self.dialog_parent()
        )
        if dialog.exec():
            self.refresh_all()

    def open_settings_dialog(self) -> None:
        if self.service is None:
            return
        dialog = FinanceSettingsDialog(self.service, parent=self.dialog_parent())
        if dialog.exec():
            self.apply_palette(self.palette)
            self.refresh_all()

    def delete_transfer(self, transfer_id: int) -> None:
        if self.service is None:
            return
        try:
            transfer = self.service.transfers.get(transfer_id)
        except FinanceError as exc:
            QMessageBox.warning(self.dialog_parent(), "无法删除", str(exc))
            return
        answer = QMessageBox.question(
            self.dialog_parent(),
            "删除资金调动",
            f"确定删除「{transfer.from_name} → {transfer.to_name} "
            f"{self.service.money(transfer.amount_cents)}」这条调动记录吗？\n"
            "删除后两个分区的余额会还原；它本来就没有计入收入/支出。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.transfers.delete(transfer_id)
        except FinanceError as exc:
            QMessageBox.warning(self.dialog_parent(), "无法删除", str(exc))
            return
        self.service.after_change()
        self.refresh_all()

    def set_account_archived(self, account_id: int, archived: bool) -> None:
        if self.service is None:
            return
        try:
            self.service.accounts.set_archived(account_id, archived)
        except FinanceError as exc:
            QMessageBox.warning(self.dialog_parent(), "操作失败", str(exc))
            return
        self.service.after_change()
        self.refresh_all()

    def delete_account(self, account_id: int) -> None:
        if self.service is None:
            return
        try:
            account = self.service.accounts.get(account_id)
        except FinanceError as exc:
            QMessageBox.warning(self.dialog_parent(), "无法删除", str(exc))
            return
        answer = QMessageBox.question(
            self.dialog_parent(),
            "删除资金分区",
            f"确定删除「{account.name}」吗？\n"
            "只有没有任何收支/转账记录、且余额为 0 的分区才能删除；"
            "有历史记录的分区建议归档。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.accounts.delete(account_id)
        except FinanceError as exc:
            QMessageBox.warning(self.dialog_parent(), "无法删除", str(exc))
            return
        self.service.after_change()
        self.refresh_all()
