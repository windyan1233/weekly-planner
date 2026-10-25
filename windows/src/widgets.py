"""可复用的通用控件。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .theme import current_palette


class FlowLayout(QLayout):
    """自动换行的水平布局（用于筛选标签，窗口变窄时不会溢出）。"""

    def __init__(self, parent: QWidget | None = None, margin: int = 0, hspacing: int = 6, vspacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:  # noqa: N802 - Qt 接口
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            space_x = self._hspacing
            space_y = self._vspacing
            next_y = y + line_height + space_y
            if x + item.sizeHint().width() > effective.right() and line_height > 0:
                x = effective.x()
                y = next_y
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += item.sizeHint().width() + space_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y() + margins.bottom()


class ElidedLabel(QLabel):
    """单行省略文本。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        super().setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setToolTip(text)
        self.update()

    def full_text(self) -> str:
        return self._full_text

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        metrics = painter.fontMetrics()
        text = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), int(self.alignment()), text)


def make_chip(text: str, *, checkable: bool = True) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("FilterChip")
    button.setCheckable(checkable)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return button


def make_icon_button(icon, tooltip: str = "", size: int = 20) -> QPushButton:
    button = QPushButton()
    button.setObjectName("IconButton")
    button.setIcon(icon)
    button.setIconSize(QSize(size, size))
    button.setFixedSize(34, 32)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


def make_toggle_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("Segmented")
    button.setCheckable(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, *, soft: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("SoftCard" if soft else "Card")


class Separator(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Separator")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class ReminderPopup(QWidget):
    """应用内提醒浮窗：始终可用的兜底提醒（带操作按钮）。"""

    view_requested = Signal(int)
    snooze_requested = Signal(object)
    dismissed = Signal()

    def __init__(self, title: str, body: str, *, task_id: int, reminder_id: int | None, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("PopupRoot")
        self._task_id = task_id
        self._reminder_id = reminder_id
        palette = current_palette()
        self.setStyleSheet(
            f"""
            QWidget#PopupRoot {{
                background-color: {palette.surface};
                border: 1px solid {palette.border_strong};
                border-radius: 14px;
            }}
            QLabel#PopupTitle {{ font-size: 14px; font-weight: 600; color: {palette.text}; }}
            QLabel#PopupBody {{ color: {palette.text_secondary}; font-size: 12px; }}
            QPushButton#PopupView {{
                background-color: {palette.accent}; color: {palette.on_accent};
                border: none; border-radius: 8px; padding: 6px 14px; font-weight: 600;
            }}
            QPushButton#PopupView:hover {{ background-color: {palette.accent_hover}; }}
            QPushButton#PopupSnooze {{
                background-color: transparent; color: {palette.text_secondary};
                border: 1px solid {palette.border}; border-radius: 8px; padding: 6px 12px;
            }}
            QPushButton#PopupSnooze:hover {{ background-color: {palette.surface_hover}; }}
            QPushButton#PopupClose {{
                background: transparent; border: none; color: {palette.text_muted};
                font-size: 16px; padding: 0px; border-radius: 8px;
            }}
            QPushButton#PopupClose:hover {{ background-color: {palette.surface_hover}; }}
            """
        )
        self.setFixedWidth(360)
        self.setWindowTitle(title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 14, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        icon_label = QLabel()
        icon_label.setPixmap(icons.bell_icon(palette.accent, 18).pixmap(18, 18))
        header.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        title_label = QLabel(title)
        title_label.setObjectName("PopupTitle")
        title_label.setWordWrap(True)
        header.addWidget(title_label, 1)
        close_button = QPushButton("×")
        close_button.setObjectName("PopupClose")
        close_button.setFixedSize(24, 24)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self._dismiss)
        header.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        body_label = QLabel(body)
        body_label.setObjectName("PopupBody")
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        if task_id:
            view_button = QPushButton("查看任务")
            view_button.setObjectName("PopupView")
            view_button.setCursor(Qt.CursorShape.PointingHandCursor)
            view_button.clicked.connect(self._view)
            buttons.addWidget(view_button)
        if reminder_id is not None:
            snooze_button = QPushButton("稍后提醒")
            snooze_button.setObjectName("PopupSnooze")
            snooze_button.setCursor(Qt.CursorShape.PointingHandCursor)
            snooze_button.clicked.connect(self._snooze)
            buttons.addWidget(snooze_button)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(25000)
        self._timer.timeout.connect(self._dismiss)

    # ------------------------------------------------------------------
    def show_at(self, anchor_rect: QRect) -> None:
        self.adjustSize()
        x = anchor_rect.right() - self.width() - 8
        y = anchor_rect.bottom() - self.height() - 8
        self.move(max(anchor_rect.left() + 8, x), max(anchor_rect.top() + 8, y))
        self.show()
        self.raise_()
        self._timer.start()

    def _view(self) -> None:
        self.view_requested.emit(self._task_id)
        self._finish()

    def _snooze(self) -> None:
        self.snooze_requested.emit(self._reminder_id)
        self._finish()

    def _dismiss(self) -> None:
        self._finish()

    def _finish(self) -> None:
        self._timer.stop()
        self.dismissed.emit()
        self.close()
        self.deleteLater()


def tint(color: str, alpha: int) -> "QColor":  # noqa: F821 - QColor 延迟导入
    from PySide6.QtGui import QColor

    c = QColor(color)
    c.setAlpha(alpha)
    return c


def mix(color_a: str, color_b: str, ratio: float) -> "QColor":
    from PySide6.QtGui import QColor

    a = QColor(color_a)
    b = QColor(color_b)
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        int(a.red() * (1 - ratio) + b.red() * ratio),
        int(a.green() * (1 - ratio) + b.green() * ratio),
        int(a.blue() * (1 - ratio) + b.blue() * ratio),
    )


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def add_form_row(layout, label_text: str, widget: QWidget) -> QLabel:
    label = QLabel(label_text)
    label.setObjectName("Muted")
    layout.addWidget(label, 0)
    layout.addWidget(widget, 1)
    return label
