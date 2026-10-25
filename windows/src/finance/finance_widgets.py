"""记账模块的通用界面组件（卡片、金额、环形图、分类条等）。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import finance_icons
from .finance_models import CategoryStat, Transaction, category_color


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def _rgba(color: str, alpha: float) -> str:
    """把 #RRGGBB 转成 Qt 能识别的 rgba()，用于柔和底色。"""
    try:
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
    except (ValueError, IndexError):
        red, green, blue = 140, 145, 166
    return f"rgba({red}, {green}, {blue}, {alpha:.2f})"


class ClickableFrame(QFrame):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class MoneyLabel(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FinanceValue")

    def set_money(self, text: str, tone: str = "") -> None:
        self.setText(text)
        target = {"in": "MoneyIn", "out": "MoneyOut", "muted": "MoneyMuted"}.get(tone, "FinanceValue")
        if self.objectName() != target:
            self.setObjectName(target)
            _repolish(self)


class StatCard(QFrame):
    """一个统计卡片：标题 + 金额 + 辅助说明。"""

    def __init__(
        self,
        title: str,
        *,
        icon: QIcon | None = None,
        parent: QWidget | None = None,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        if icon is not None:
            icon_label = QLabel()
            icon_label.setPixmap(icon.pixmap(16, 16))
            header.addWidget(icon_label)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("Muted")
        header.addWidget(self.title_label)
        header.addStretch(1)
        layout.addLayout(header)

        self.value_label = QLabel("—")
        self.value_label.setObjectName("FinanceValueSm" if compact else "FinanceValue")
        layout.addWidget(self.value_label)

        self.sub_label = QLabel("")
        self.sub_label.setObjectName("Muted")
        self.sub_label.setWordWrap(True)
        layout.addWidget(self.sub_label)

    def set_value(self, text: str, tone: str = "") -> None:
        self.value_label.setText(text)
        target = {"in": "MoneyIn", "out": "MoneyOut", "muted": "MoneyMuted"}.get(
            tone, "FinanceValueSm" if self.value_label.objectName() == "FinanceValueSm" else "FinanceValue"
        )
        if self.value_label.objectName() != target:
            self.value_label.setObjectName(target)
            _repolish(self.value_label)

    def set_sub(self, text: str) -> None:
        self.sub_label.setText(text)
        self.sub_label.setVisible(bool(text))


class SectionCard(QFrame):
    """带标题的卡片，可以放一个右上角操作按钮。"""

    def __init__(
        self,
        title: str,
        *,
        subtitle: str = "",
        parent: QWidget | None = None,
        margins: tuple[int, int, int, int] = (18, 14, 18, 16),
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(*margins)
        self.outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")
        title_box.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Muted")
        self.subtitle_label.setVisible(bool(subtitle))
        title_box.addWidget(self.subtitle_label)
        header.addLayout(title_box)
        header.addStretch(1)
        self.header_layout = header
        self.outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self.outer.addLayout(self.body)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class RatioBar(QWidget):
    def __init__(self, color: str = "#5B6BD6", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self._ratio = 0.0
        self._track = "#EEF0F6"
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_palette(self, palette) -> None:
        self._track = palette.surface_alt
        self.update()

    def set_value(self, ratio: float, color: str | None = None) -> None:
        self._ratio = max(0.0, min(100.0, ratio))
        if color:
            self._color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = self.height() / 2
        painter.setBrush(QColor(self._track))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), radius, radius)
        if self._ratio > 0:
            width = max(radius * 2, self.width() * self._ratio / 100.0)
            painter.setBrush(QColor(self._color))
            painter.drawRoundedRect(QRectF(0, 0, min(width, self.width()), self.height()), radius, radius)


class DonutChart(QWidget):
    """六类支出的环形图（数据来自真实账目）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segments: list[tuple[str, int]] = []
        self._center_top = "本月支出"
        self._center_value = "—"
        self._text_color = "#1D2130"
        self._muted = "#8A91A6"
        self._track = "#EEF0F6"
        self.setMinimumSize(210, 210)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def set_palette(self, palette) -> None:
        self._text_color = palette.text
        self._muted = palette.text_muted
        self._track = palette.surface_alt
        self.update()

    def set_data(self, segments: list[tuple[str, int]], center_value: str) -> None:
        self._segments = segments
        self._center_value = center_value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height()) - 12
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        thickness = max(16.0, side * 0.15)
        inner = rect.adjusted(thickness, thickness, -thickness, -thickness)
        total = sum(value for _color, value in self._segments)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._track))
        path = QPainterPath()
        path.addEllipse(rect)
        inner_path = QPainterPath()
        inner_path.addEllipse(inner)
        painter.drawPath(path.subtracted(inner_path))
        if total > 0:
            start = 90 * 16
            for color, value in self._segments:
                if value <= 0:
                    continue
                span = -int(value / total * 360 * 16)
                ring = QPainterPath()
                ring.addEllipse(rect)
                hole = QPainterPath()
                hole.addEllipse(inner)
                ring = ring.subtracted(hole)
                painter.setClipPath(ring)
                painter.setBrush(QColor(color))
                painter.drawPie(rect, start, span)
                painter.setClipping(False)
                start += span

        # 中心文字
        font = QFont()
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor(self._muted))
        painter.drawText(
            QRectF(0, rect.center().y() - 26, self.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            self._center_top,
        )
        value_font = QFont()
        value_font.setPixelSize(18)
        value_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(value_font)
        painter.setPen(QColor(self._text_color))
        painter.drawText(
            QRectF(0, rect.center().y() - 6, self.width(), 28),
            Qt.AlignmentFlag.AlignCenter,
            self._center_value,
        )


class CategoryRow(ClickableFrame):
    """分类行：图标 + 名称 + 占比条 + 金额 + 与上月变化。"""

    def __init__(self, palette=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FinanceRow")
        self._stat: CategoryStat | None = None
        self._palette = palette
        self._tone = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(22, 22)
        self.icon_label.setPixmap(finance_icons.category_icon("food", size=18).pixmap(18, 18))
        layout.addWidget(self.icon_label)

        self.name_label = QLabel("")
        self.name_label.setObjectName("CategoryName")
        self.name_label.setFixedWidth(56)
        layout.addWidget(self.name_label)

        self.bar = RatioBar()
        if palette is not None:
            self.bar.set_palette(palette)
        layout.addWidget(self.bar, 1)

        self.ratio_label = QLabel("0%")
        self.ratio_label.setObjectName("Muted")
        self.ratio_label.setFixedWidth(46)
        self.ratio_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.ratio_label)

        self.amount_label = QLabel("¥0.00")
        self.amount_label.setObjectName("CategoryAmount")
        self.amount_label.setFixedWidth(96)
        self.amount_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.amount_label)

        self.delta_label = QLabel("")
        self.delta_label.setObjectName("CategoryDelta")
        self.delta_label.setFixedWidth(78)
        self.delta_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.delta_label)

    @property
    def stat(self) -> CategoryStat | None:
        return self._stat

    def set_data(self, stat: CategoryStat, money) -> None:
        self._stat = stat
        self.icon_label.setPixmap(finance_icons.category_icon(stat.key, stat.color, 18).pixmap(18, 18))
        self.name_label.setText(stat.label)
        self.bar.set_value(stat.ratio, stat.color)
        self.ratio_label.setText(f"{stat.ratio:.1f}%")
        self.amount_label.setText(money(stat.amount_cents))
        self.delta_label.setText(self._delta_text(stat))
        self._tone = self._delta_tone(stat)
        self._apply_delta_color()

    def set_palette(self, palette) -> None:
        self._palette = palette
        self.bar.set_palette(palette)
        self._apply_delta_color()

    def _apply_delta_color(self) -> None:
        palette = self._palette
        if self._tone == "up":
            color = palette.danger if palette is not None else "#D2606B"
        elif self._tone == "down":
            color = palette.success if palette is not None else "#4C9E78"
        else:
            color = palette.text_muted if palette is not None else "#8A91A6"
        self.delta_label.setStyleSheet(f"font-size: 12px; color: {color};")

    @staticmethod
    def _delta_text(stat: CategoryStat) -> str:
        if stat.amount_cents == 0 and stat.prev_cents == 0:
            return "—"
        if stat.prev_cents == 0:
            return "新增" if stat.amount_cents > 0 else "—"
        delta = stat.delta_cents
        if delta == 0:
            return "持平"
        sign = "+" if delta > 0 else "−"
        return f"{sign}{abs(stat.delta_ratio or 0):.0f}%"

    @staticmethod
    def _delta_tone(stat: CategoryStat) -> str:
        if stat.prev_cents == 0 or stat.amount_cents == stat.prev_cents:
            return ""
        return "up" if stat.delta_cents > 0 else "down"


class FlowRow(ClickableFrame):
    """收支流水行。"""

    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FinanceRow")
        self._transaction: Transaction | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(28, 28)
        layout.addWidget(self.icon_label)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        self.title_label = QLabel("")
        self.title_label.setObjectName("RowTitle")
        text_box.addWidget(self.title_label)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("Muted")
        text_box.addWidget(self.meta_label)
        layout.addLayout(text_box, 1)

        self.amount_label = QLabel("")
        self.amount_label.setObjectName("AmountNeutral")
        self.amount_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.amount_label)

        self.category_label = QLabel("")
        self.category_label.setFixedWidth(74)
        self.category_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.category_label.setObjectName("Badge")
        layout.addWidget(self.category_label)

        self.clicked.connect(self._open_edit)

    def _open_edit(self) -> None:
        if self._transaction is not None:
            self.edit_requested.emit(self._transaction.id)

    @property
    def transaction(self) -> Transaction | None:
        return self._transaction

    def set_transaction(self, transaction: Transaction, money) -> None:
        self._transaction = transaction
        if transaction.kind == "income":
            key, label = "income", "收入"
            self.icon_label.setPixmap(finance_icons.finance_icon("income", "#4C9E78", 20).pixmap(20, 20))
        else:
            key = transaction.category
            label = transaction.category_label
            self.icon_label.setPixmap(
                finance_icons.category_icon(key, category_color(key), 20).pixmap(20, 20)
            )
        self.title_label.setText(
            transaction.title
            or ("未填写说明的收入" if transaction.kind == "income" else "未填写说明的支出")
        )
        meta = f"{transaction.occurred_on:%m-%d} · {transaction.account_name}"
        if transaction.note:
            meta += f" · {transaction.note}"
        self.meta_label.setText(meta)
        sign = "+" if transaction.kind == "income" else "−"
        self.amount_label.setText(f"{sign}{money(transaction.amount_cents)}")
        self.amount_label.setObjectName("AmountPositive" if transaction.kind == "income" else "AmountNegative")
        _repolish(self.amount_label)
        color = category_color(key) if key != "income" else "#4C9E78"
        self.category_label.setText(label)
        self.category_label.setStyleSheet(
            f"color: {color}; background-color: {_rgba(color, 0.14)}; "
            f"border-radius: 9px; padding: 2px 6px;"
        )


class EmptyState(QWidget):
    def __init__(
        self,
        title: str,
        hint: str = "",
        *,
        icon: QIcon | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 26, 20, 26)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon is not None:
            icon_label = QLabel()
            icon_label.setPixmap(icon.pixmap(40, 40))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("Muted")
            hint_label.setWordWrap(True)
            hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint_label.setMaximumWidth(460)
            layout.addWidget(hint_label, 0, Qt.AlignmentFlag.AlignHCenter)


class Pill(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class SegmentedControl(QWidget):
    """分段按钮（月份切换等）。"""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._buttons: dict[str, QPushButton] = {}
        self._current = options[0][0] if options else ""
        for key, label in options:
            button = QPushButton(label)
            button.setObjectName("Segmented")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, value=key: self.set_current(value))
            layout.addWidget(button)
            self._buttons[key] = button
        self.set_current(self._current, emit=False)

    def current(self) -> str:
        return self._current

    def set_current(self, key: str, *, emit: bool = True) -> None:
        if key not in self._buttons:
            return
        self._current = key
        for value, button in self._buttons.items():
            button.setChecked(value == key)
        if emit:
            self.changed.emit(key)
