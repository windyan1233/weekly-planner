"""主题：浅色 / 深色调色板 + 全局 QSS。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QApplication

from . import config


@dataclass(frozen=True)
class Palette:
    name: str
    window_bg: str
    surface: str
    surface_alt: str
    surface_hover: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str
    today_bg: str
    today_border: str
    danger: str
    danger_soft: str
    warning: str
    warning_soft: str
    success: str
    success_soft: str
    grid_line: str
    chip_bg: str
    chip_border: str
    done_text: str
    selection: str

    def color(self, key: str) -> QColor:
        return QColor(getattr(self, key))


LIGHT = Palette(
    name="light",
    window_bg="#F2F4F9",
    surface="#FFFFFF",
    surface_alt="#F7F8FC",
    surface_hover="#EEF1F9",
    border="#E4E7F0",
    border_strong="#D4D8E6",
    text="#1D2130",
    text_secondary="#4B5367",
    text_muted="#8A91A6",
    accent="#5B6BD6",
    accent_hover="#4A5AC8",
    accent_soft="#EDF0FD",
    on_accent="#FFFFFF",
    today_bg="#EEF2FF",
    today_border="#B7C2F2",
    danger="#D2606B",
    danger_soft="#FBEDEF",
    warning="#C98A2B",
    warning_soft="#FBF3E5",
    success="#4C9E78",
    success_soft="#EAF6F0",
    grid_line="#EDF0F6",
    chip_bg="#FFFFFF",
    chip_border="#E3E6F0",
    done_text="#9AA1B4",
    selection="#DDE3FB",
)

DARK = Palette(
    name="dark",
    window_bg="#161922",
    surface="#1E222C",
    surface_alt="#242936",
    surface_hover="#2A3040",
    border="#2F3542",
    border_strong="#3C4354",
    text="#E8EAF2",
    text_secondary="#C2C8D8",
    text_muted="#8C94A9",
    accent="#7C89EA",
    accent_hover="#909BF0",
    accent_soft="#272D4A",
    on_accent="#FFFFFF",
    today_bg="#222A45",
    today_border="#48559B",
    danger="#E0808A",
    danger_soft="#3A252B",
    warning="#E0AE5F",
    warning_soft="#3A3020",
    success="#6FBF97",
    success_soft="#1F342A",
    grid_line="#292E3B",
    chip_bg="#252B38",
    chip_border="#343B4B",
    done_text="#78809A",
    selection="#33406E",
)

PALETTES = {"light": LIGHT, "dark": DARK}


def resolve_theme(name: str) -> str:
    """把 system 解析成具体主题。"""
    if name in PALETTES:
        return name
    hint = QGuiApplication.styleHints().colorScheme()
    return "dark" if hint.name.lower() == "dark" else "light"


def palette_for(name: str) -> Palette:
    return PALETTES.get(resolve_theme(name), LIGHT)


# --------------------------------------------------------------------------
# 生成的资源（下拉箭头、勾选标记）
# --------------------------------------------------------------------------
_ASSET_CACHE: dict[str, str] = {}


def qss_url(path: str) -> str:
    return Path(path).as_posix()


def _write_asset(name: str, color: str, painter) -> str:
    key = f"{name}_{color.strip('#')}"
    cached = _ASSET_CACHE.get(key)
    if cached and Path(cached).exists():
        return cached
    assets = config.app_data_dir() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    path = assets / f"{key}.png"
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPainter, QPen, QPixmap

    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter(p, QColor(color))
    p.end()
    pixmap.save(str(path), "PNG")
    _ASSET_CACHE[key] = str(path)
    return str(path)


def _draw_chevron(painter, color: QColor) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPen

    pen = QPen(color, 3.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(12, 16), QPointF(20, 24), QPointF(28, 16)])


def _draw_check(painter, color: QColor) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPen

    pen = QPen(color, 3.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(11, 21), QPointF(17, 27), QPointF(29, 13)])


def ensure_theme_assets(palette: Palette) -> dict[str, str]:
    return {
        "chevron": _write_asset("chevron", palette.text_muted, _draw_chevron),
        "check": _write_asset("check", palette.on_accent, _draw_check),
    }


# --------------------------------------------------------------------------
# QSS
# --------------------------------------------------------------------------
def build_stylesheet(palette: Palette) -> str:
    p = palette
    assets = ensure_theme_assets(p)
    chevron = qss_url(assets["chevron"])
    check = qss_url(assets["check"])
    return f"""
* {{
    outline: none;
}}
QWidget {{
    color: {p.text};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background-color: {p.window_bg};
}}
QToolTip {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 6px;
    padding: 6px 8px;
}}
QFrame#Card {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: 14px;
}}
QFrame#SoftCard {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QFrame#Separator {{
    background-color: {p.border};
    max-height: 1px;
    border: none;
}}
QLabel {{
    background: transparent;
    color: {p.text};
}}
QLabel#Title {{
    font-size: 22px;
    font-weight: 600;
}}
QLabel#Subtitle {{
    color: {p.text_muted};
    font-size: 12px;
}}
QLabel#Muted {{
    color: {p.text_muted};
}}
QLabel#SectionTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {p.text_secondary};
}}
QLabel#ClockLabel {{
    color: {p.text_secondary};
    font-size: 12px;
    font-feature-settings: "tnum";
}}
QLabel#ErrorLabel {{
    color: {p.danger};
    background-color: {p.danger_soft};
    border-radius: 8px;
    padding: 8px 10px;
}}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QComboBox {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 9px;
    padding: 6px 10px;
    selection-background-color: {p.accent};
    selection-color: {p.on_accent};
    min-height: 20px;
}}
QLineEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDateEdit:hover,
QTimeEdit:hover, QComboBox:hover {{
    border-color: {p.border_strong};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QComboBox:focus {{
    border-color: {p.accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    color: {p.text_muted};
    background-color: {p.surface_alt};
}}
QLineEdit#SearchInput {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 7px 10px 7px 30px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url({chevron});
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
    outline: none;
}}
QDateEdit::drop-down, QTimeEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 20px;
    border: none;
    background: transparent;
}}
QDateEdit::down-arrow, QTimeEdit::down-arrow {{
    image: url({chevron});
    width: 9px;
    height: 9px;
}}
QTimeEdit::up-button, QTimeEdit::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 14px;
    border: none;
    background: transparent;
    subcontrol-origin: border;
}}
QTimeEdit::up-arrow, QTimeEdit::down-arrow,
QSpinBox::up-arrow, QSpinBox::down-arrow {{
    width: 7px;
    height: 7px;
}}
QTimeEdit {{
    padding-right: 4px;
}}
QPlainTextEdit {{
    padding: 8px 10px;
}}
QPushButton {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 9px;
    padding: 7px 14px;
    min-height: 20px;
}}
QPushButton:hover {{
    background-color: {p.surface_hover};
    border-color: {p.border_strong};
}}
QPushButton:pressed {{
    background-color: {p.accent_soft};
}}
QPushButton:disabled {{
    color: {p.text_muted};
    background-color: {p.surface_alt};
    border-color: {p.border};
}}
QPushButton#Primary {{
    background-color: {p.accent};
    color: {p.on_accent};
    border: 1px solid {p.accent};
    font-weight: 600;
    padding: 8px 18px;
}}
QPushButton#Primary:hover {{
    background-color: {p.accent_hover};
    border-color: {p.accent_hover};
}}
QPushButton#Primary:pressed {{
    background-color: {p.accent};
}}
QPushButton#Danger {{
    color: {p.danger};
    border-color: {p.danger};
}}
QPushButton#Danger:hover {{
    background-color: {p.danger_soft};
}}
QPushButton#DangerGhost {{
    background: transparent;
    border: none;
    color: {p.danger};
    padding: 6px 10px;
}}
QPushButton#DangerGhost:hover {{
    background-color: {p.danger_soft};
    border-radius: 8px;
}}
QPushButton#Ghost {{
    background-color: transparent;
    border-color: transparent;
    color: {p.text_secondary};
}}
QPushButton#Ghost:hover {{
    background-color: {p.surface_hover};
    color: {p.text};
}}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {p.accent};
    padding: 2px 4px;
    text-decoration: underline;
}}
QPushButton#IconButton {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 9px;
    padding: 6px;
}}
QPushButton#IconButton:hover {{
    background-color: {p.surface_hover};
    border-color: {p.border_strong};
}}
QPushButton#FilterChip {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 13px;
    padding: 4px 12px;
    color: {p.text_secondary};
    min-height: 16px;
}}
QPushButton#FilterChip:hover {{
    background-color: {p.surface_hover};
    color: {p.text};
}}
QPushButton#FilterChip:checked {{
    background-color: {p.accent_soft};
    border-color: {p.today_border};
    color: {p.accent};
    font-weight: 600;
}}
QPushButton#Segmented {{
    background-color: transparent;
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 14px;
    color: {p.text_secondary};
}}
QPushButton#Segmented:checked {{
    background-color: {p.accent_soft};
    border-color: {p.accent};
    color: {p.accent};
    font-weight: 600;
}}
QPushButton#OverdueChip {{
    background-color: {p.danger_soft};
    border: 1px solid {p.danger};
    color: {p.danger};
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 12px;
}}
QPushButton#OverdueChip:hover {{
    background-color: {p.surface_hover};
}}
QCheckBox {{
    spacing: 8px;
    color: {p.text};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {p.border_strong};
    background-color: {p.surface};
}}
QCheckBox::indicator:hover {{
    border-color: {p.accent};
}}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
    image: url({check});
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px 0 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: 4px;
    min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.text_muted};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    border-radius: 4px;
    min-width: 36px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
    width: 0px;
}}
QMenu {{
    background-color: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px 7px 14px;
    border-radius: 7px;
    color: {p.text};
}}
QMenu::item:selected {{
    background-color: {p.accent_soft};
    color: {p.accent};
}}
QMenu::separator {{
    height: 1px;
    background-color: {p.border};
    margin: 5px 8px;
}}
QCalendarWidget QWidget {{
    alternate-background-color: {p.surface_alt};
}}
QCalendarWidget QAbstractItemView:enabled {{
    background-color: {p.surface};
    color: {p.text};
    selection-background-color: {p.accent};
    selection-color: {p.on_accent};
}}
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 8px;
}}
QListWidget::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text};
}}
QListWidget::item:hover {{
    background-color: {p.surface_hover};
}}
QStatusBar {{
    background: transparent;
    color: {p.text_muted};
}}
QSplitter::handle {{
    background: transparent;
}}

/* ---------- 记账模块 ---------- */
QPushButton#NavTab {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 6px 14px;
    color: {p.text_secondary};
    font-weight: 500;
}}
QPushButton#NavTab:hover {{
    background-color: {p.surface_hover};
    color: {p.text};
}}
QPushButton#NavTab:checked {{
    background-color: {p.accent_soft};
    border-color: {p.today_border};
    color: {p.accent};
    font-weight: 600;
}}
QLabel#NavBrand {{
    font-size: 15px;
    font-weight: 600;
}}
QPushButton#IncomeButton {{
    background-color: {p.success_soft};
    border: 1px solid {p.success};
    color: {p.success};
    font-weight: 600;
    padding: 8px 16px;
}}
QPushButton#IncomeButton:hover {{
    background-color: {p.surface_hover};
}}
QPushButton#ExpenseButton {{
    background-color: {p.danger_soft};
    border: 1px solid {p.danger};
    color: {p.danger};
    font-weight: 600;
    padding: 8px 16px;
}}
QPushButton#ExpenseButton:hover {{
    background-color: {p.surface_hover};
}}
QLabel#BalanceValue {{
    font-size: 30px;
    font-weight: 600;
}}
QLabel#FinanceValue {{
    font-size: 25px;
    font-weight: 600;
}}
QLabel#FinanceValueSm {{
    font-size: 19px;
    font-weight: 600;
}}
QLabel#MoneyIn {{
    font-size: 19px;
    font-weight: 600;
    color: {p.success};
}}
QLabel#MoneyOut {{
    font-size: 19px;
    font-weight: 600;
    color: {p.danger};
}}
QLabel#MoneyMuted {{
    font-size: 19px;
    font-weight: 600;
    color: {p.text_secondary};
}}
QLabel#RowTitle {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#CategoryName {{
    font-size: 13px;
    font-weight: 500;
}}
QLabel#CategoryAmount {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#CategoryDelta {{
    font-size: 12px;
    color: {p.text_muted};
}}
QLabel#CategoryDelta[financeTone="up"] {{
    color: {p.danger};
}}
QLabel#CategoryDelta[financeTone="down"] {{
    color: {p.success};
}}
QLabel#HistoryClosing {{
    font-size: 12px;
    color: {p.text_secondary};
}}
QLabel#SummaryText {{
    font-size: 13px;
}}
QLabel#Pill {{
    background-color: {p.accent_soft};
    color: {p.accent};
    border-radius: 8px;
    padding: 1px 8px;
    font-size: 11px;
}}
QLabel[financeTone="up"] {{
    color: {p.danger};
}}
QLabel[financeTone="down"] {{
    color: {p.success};
}}
QFrame#FinanceRow {{
    border: none;
    border-radius: 8px;
}}
QFrame#FinanceRow:hover {{
    background-color: {p.surface_hover};
}}
QFrame#HistoryCard {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 10px;
}}
QFrame#HistoryCard:hover {{
    background-color: {p.surface_hover};
    border-color: {p.border_strong};
}}
QFrame#HistoryCard[selected="true"] {{
    background-color: {p.accent_soft};
    border-color: {p.today_border};
}}
QPushButton#CatChip {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 9px;
    padding: 7px 10px;
    color: {p.text_secondary};
}}
QPushButton#CatChip:hover {{
    border-color: {p.border_strong};
    color: {p.text};
}}
QPushButton#CatChip:checked {{
    background-color: {p.accent_soft};
    border-color: {p.accent};
    color: {p.accent};
    font-weight: 600;
}}
QLabel#AmountPositive {{
    color: {p.success};
    font-weight: 600;
}}
QLabel#AmountNegative {{
    color: {p.danger};
    font-weight: 600;
}}
QLabel#AmountNeutral {{
    color: {p.text_secondary};
    font-weight: 600;
}}
"""


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._setting = "light"
        self._palette = LIGHT

    @property
    def setting(self) -> str:
        return self._setting

    @property
    def palette(self) -> Palette:
        return self._palette

    @property
    def resolved(self) -> str:
        return self._palette.name

    def apply(self, setting: str) -> str:
        self._setting = setting
        self._palette = palette_for(setting)
        set_current_palette(self._palette)
        self._app.setStyleSheet(build_stylesheet(self._palette))
        self.theme_changed.emit(self._palette.name)
        return self._palette.name

    def is_dark(self) -> bool:
        return self._palette.name == "dark"

    def palette_dict(self) -> dict[str, str]:
        return asdict(self._palette)


# 供不支持注入 ThemeManager 的简单控件使用
_CURRENT: Palette = LIGHT


def current_palette() -> Palette:
    return _CURRENT


def set_current_palette(palette: Palette) -> None:
    global _CURRENT
    _CURRENT = palette
