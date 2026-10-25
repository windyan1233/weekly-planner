"""用 QPainter 绘制的小图标（不依赖任何外部资源文件）。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from . import config


def _canvas(size: int, scale: int = 3) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(float(scale))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return pixmap, painter


def _pen(color: str, width: float = 1.8) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def chevron_icon(direction: str, color: str, size: int = 18) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 2.0))
    mid = size / 2
    offset = size * 0.16
    if direction == "left":
        points = [QPointF(mid + offset, mid - offset * 1.4), QPointF(mid - offset, mid), QPointF(mid + offset, mid + offset * 1.4)]
    else:
        points = [QPointF(mid - offset, mid - offset * 1.4), QPointF(mid + offset, mid), QPointF(mid - offset, mid + offset * 1.4)]
    painter.drawPolyline(points)
    painter.end()
    return QIcon(pixmap)


def plus_icon(color: str, size: int = 18) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 2.1))
    painter.drawLine(QPointF(size * 0.5, size * 0.26), QPointF(size * 0.5, size * 0.74))
    painter.drawLine(QPointF(size * 0.26, size * 0.5), QPointF(size * 0.74, size * 0.5))
    painter.end()
    return QIcon(pixmap)


def search_icon(color: str, size: int = 18) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 1.9))
    radius = size * 0.24
    painter.drawEllipse(QPointF(size * 0.44, size * 0.44), radius, radius)
    painter.drawLine(
        QPointF(size * 0.62, size * 0.62), QPointF(size * 0.78, size * 0.78)
    )
    painter.end()
    return QIcon(pixmap)


def close_icon(color: str, size: int = 14) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 1.9))
    painter.drawLine(QPointF(size * 0.28, size * 0.28), QPointF(size * 0.72, size * 0.72))
    painter.drawLine(QPointF(size * 0.72, size * 0.28), QPointF(size * 0.28, size * 0.72))
    painter.end()
    return QIcon(pixmap)


def check_icon(color: str, size: int = 16) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 2.0))
    painter.drawPolyline(
        [
            QPointF(size * 0.24, size * 0.52),
            QPointF(size * 0.42, size * 0.70),
            QPointF(size * 0.78, size * 0.30),
        ]
    )
    painter.end()
    return QIcon(pixmap)


def clock_icon(color: str, size: int = 16) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 1.6))
    painter.drawEllipse(QRectF(size * 0.18, size * 0.18, size * 0.64, size * 0.64))
    painter.drawLine(QPointF(size * 0.5, size * 0.34), QPointF(size * 0.5, size * 0.52))
    painter.drawLine(QPointF(size * 0.5, size * 0.52), QPointF(size * 0.63, size * 0.6))
    painter.end()
    return QIcon(pixmap)


def bell_icon(color: str, size: int = 16) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 1.6))
    path = QPainterPath()
    path.moveTo(size * 0.28, size * 0.66)
    path.lineTo(size * 0.72, size * 0.66)
    path.cubicTo(
        size * 0.68, size * 0.56, size * 0.7, size * 0.44,
        size * 0.66, size * 0.34,
    )
    path.cubicTo(
        size * 0.62, size * 0.2, size * 0.38, size * 0.2,
        size * 0.34, size * 0.34,
    )
    path.cubicTo(size * 0.3, size * 0.44, size * 0.32, size * 0.56, size * 0.28, size * 0.66)
    painter.drawPath(path)
    painter.drawArc(QRectF(size * 0.42, size * 0.68, size * 0.16, size * 0.14), 0, 180 * 16)
    painter.end()
    return QIcon(pixmap)


def edit_icon(color: str, size: int = 16) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 1.6))
    painter.drawLine(QPointF(size * 0.3, size * 0.7), QPointF(size * 0.7, size * 0.3))
    painter.drawLine(QPointF(size * 0.26, size * 0.74), QPointF(size * 0.38, size * 0.72))
    painter.drawLine(QPointF(size * 0.62, size * 0.38), QPointF(size * 0.26, size * 0.74))
    painter.end()
    return QIcon(pixmap)


def trash_icon(color: str, size: int = 16) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 1.5))
    painter.drawLine(QPointF(size * 0.26, size * 0.32), QPointF(size * 0.74, size * 0.32))
    painter.drawLine(QPointF(size * 0.4, size * 0.24), QPointF(size * 0.6, size * 0.24))
    painter.drawPolyline(
        [
            QPointF(size * 0.34, size * 0.32),
            QPointF(size * 0.38, size * 0.76),
            QPointF(size * 0.62, size * 0.76),
            QPointF(size * 0.66, size * 0.32),
        ]
    )
    painter.end()
    return QIcon(pixmap)


def copy_icon(color: str, size: int = 16) -> QIcon:
    pixmap, painter = _canvas(size)
    painter.setPen(_pen(color, 1.5))
    painter.drawRoundedRect(QRectF(size * 0.3, size * 0.3, size * 0.38, size * 0.38), 2, 2)
    painter.drawPolyline(
        [
            QPointF(size * 0.24, size * 0.44),
            QPointF(size * 0.24, size * 0.72),
            QPointF(size * 0.52, size * 0.72),
            QPointF(size * 0.52, size * 0.68),
        ]
    )
    painter.end()
    return QIcon(pixmap)


def calendar_logo(size: int = 64) -> QPixmap:
    """应用图标：圆角日历卡片。"""
    pixmap = QPixmap(size * 4, size * 4)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(4.0)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#6E7BE8"))
    gradient.setColorAt(1.0, QColor("#8E7BE0"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.26, size * 0.26)
    painter.fillPath(path, gradient)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawRoundedRect(QRectF(size * 0.22, size * 0.30, size * 0.56, size * 0.44), size * 0.08, size * 0.08)
    painter.setPen(QPen(QColor("#5B6BD6"), size * 0.045))
    painter.drawLine(
        QPointF(size * 0.22, size * 0.43), QPointF(size * 0.78, size * 0.43)
    )
    painter.setPen(QPen(QColor("#5B6BD6"), size * 0.06, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(size * 0.34, size * 0.22), QPointF(size * 0.34, size * 0.32))
    painter.drawLine(QPointF(size * 0.66, size * 0.22), QPointF(size * 0.66, size * 0.32))
    painter.setBrush(QColor("#5B6BD6"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(size * 0.40, size * 0.58), size * 0.045, size * 0.045)
    painter.drawEllipse(QPointF(size * 0.60, size * 0.58), size * 0.045, size * 0.045)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(calendar_logo(size))
    return icon


def app_icon_path() -> str:
    """把图标写入数据目录，便于 PyInstaller / 快捷方式使用。"""
    path = config.app_data_dir() / "assets" / "app.ico"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pixmap = calendar_logo(256)
        pixmap.save(str(path), "ICO")
    return str(path)
