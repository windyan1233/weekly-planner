"""记账模块的小图标（QPainter 绘制，不依赖外部资源）。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from .finance_models import CATEGORY_COLORS


def _canvas(size: int, scale: int = 3) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(float(scale))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return pixmap, painter


def _pen(color: str, width: float = 1.7) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _star_path(center: QPointF, outer: float, inner: float) -> QPainterPath:
    path = QPainterPath()
    for index in range(10):
        radius = outer if index % 2 == 0 else inner
        angle = -math.pi / 2 + index * math.pi / 5
        point = QPointF(
            center.x() + radius * math.cos(angle),
            center.y() + radius * math.sin(angle),
        )
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def _draw_category(painter: QPainter, key: str, size: float, color: str) -> None:
    painter.setPen(_pen(color, max(1.4, size * 0.075)))
    s = size

    if key == "food":  # 碗 + 蒸汽
        painter.drawLine(QPointF(s * 0.16, s * 0.48), QPointF(s * 0.84, s * 0.48))
        path = QPainterPath(QPointF(s * 0.2, s * 0.48))
        path.quadTo(QPointF(s * 0.5, s * 0.86), QPointF(s * 0.8, s * 0.48))
        painter.drawPath(path)
        painter.drawLine(QPointF(s * 0.38, s * 0.38), QPointF(s * 0.38, s * 0.24))
        painter.drawLine(QPointF(s * 0.56, s * 0.38), QPointF(s * 0.56, s * 0.2))
    elif key == "life":  # 购物袋
        painter.drawRoundedRect(QRectF(s * 0.2, s * 0.38, s * 0.6, s * 0.44), s * 0.09, s * 0.09)
        path = QPainterPath(QPointF(s * 0.34, s * 0.4))
        path.quadTo(QPointF(s * 0.5, s * 0.16), QPointF(s * 0.66, s * 0.4))
        painter.drawPath(path)
    elif key == "stationery":  # 笔
        painter.drawLine(QPointF(s * 0.3, s * 0.74), QPointF(s * 0.74, s * 0.28))
        painter.drawLine(QPointF(s * 0.66, s * 0.2), QPointF(s * 0.8, s * 0.34))
        tip = QPainterPath(QPointF(s * 0.22, s * 0.66))
        tip.lineTo(QPointF(s * 0.16, s * 0.84))
        tip.lineTo(QPointF(s * 0.34, s * 0.78))
        tip.closeSubpath()
        painter.drawPath(tip)
    elif key == "game":  # 手柄
        painter.drawRoundedRect(QRectF(s * 0.12, s * 0.32, s * 0.76, s * 0.4), s * 0.18, s * 0.18)
        painter.drawLine(QPointF(s * 0.3, s * 0.44), QPointF(s * 0.3, s * 0.6))
        painter.drawLine(QPointF(s * 0.22, s * 0.52), QPointF(s * 0.38, s * 0.52))
        painter.drawPoint(QPointF(s * 0.66, s * 0.46))
        painter.drawPoint(QPointF(s * 0.73, s * 0.56))
    elif key == "merch":  # 星星
        painter.drawPath(_star_path(QPointF(s * 0.5, s * 0.52), s * 0.3, s * 0.13))
    elif key == "tech":  # 芯片
        painter.drawRoundedRect(QRectF(s * 0.3, s * 0.3, s * 0.4, s * 0.4), s * 0.08, s * 0.08)
        painter.drawRect(QRectF(s * 0.42, s * 0.42, s * 0.16, s * 0.16))
        for ratio in (0.38, 0.62):
            painter.drawLine(QPointF(s * ratio, s * 0.2), QPointF(s * ratio, s * 0.3))
            painter.drawLine(QPointF(s * ratio, s * 0.7), QPointF(s * ratio, s * 0.8))
            painter.drawLine(QPointF(s * 0.2, s * ratio), QPointF(s * 0.3, s * ratio))
            painter.drawLine(QPointF(s * 0.7, s * ratio), QPointF(s * 0.8, s * ratio))
    else:  # 自定义分类：标签形状
        path = QPainterPath(QPointF(s * 0.24, s * 0.5))
        path.lineTo(QPointF(s * 0.5, s * 0.22))
        path.lineTo(QPointF(s * 0.8, s * 0.22))
        path.lineTo(QPointF(s * 0.8, s * 0.52))
        path.lineTo(QPointF(s * 0.5, s * 0.8))
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawEllipse(QPointF(s * 0.62, s * 0.4), s * 0.05, s * 0.05)


def _draw_icon(painter: QPainter, name: str, size: float, color: str) -> None:
    painter.setPen(_pen(color, max(1.4, size * 0.08)))
    s = size
    if name == "wallet":
        painter.drawRoundedRect(QRectF(s * 0.14, s * 0.28, s * 0.72, s * 0.46), s * 0.1, s * 0.1)
        painter.drawLine(QPointF(s * 0.14, s * 0.4), QPointF(s * 0.86, s * 0.4))
        painter.drawEllipse(QPointF(s * 0.68, s * 0.6), s * 0.055, s * 0.055)
    elif name == "chart":
        painter.drawLine(QPointF(s * 0.18, s * 0.82), QPointF(s * 0.84, s * 0.82))
        painter.drawRoundedRect(QRectF(s * 0.24, s * 0.52, s * 0.12, s * 0.3), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(s * 0.44, s * 0.36, s * 0.12, s * 0.46), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(s * 0.64, s * 0.22, s * 0.12, s * 0.6), 1.5, 1.5)
    elif name == "layers":
        painter.drawPolyline(
            [
                QPointF(s * 0.5, s * 0.2),
                QPointF(s * 0.84, s * 0.38),
                QPointF(s * 0.5, s * 0.56),
                QPointF(s * 0.16, s * 0.38),
                QPointF(s * 0.5, s * 0.2),
            ]
        )
        painter.drawPolyline(
            [QPointF(s * 0.16, s * 0.56), QPointF(s * 0.5, s * 0.74), QPointF(s * 0.84, s * 0.56)]
        )
    elif name in ("income", "expense"):
        down = name == "income"
        y0, y1 = (s * 0.22, s * 0.68) if down else (s * 0.68, s * 0.22)
        painter.drawLine(QPointF(s * 0.5, y0), QPointF(s * 0.5, y1))
        wing = s * 0.16
        if down:
            painter.drawPolyline(
                [QPointF(s * 0.5 - wing, y1 - wing), QPointF(s * 0.5, y1), QPointF(s * 0.5 + wing, y1 - wing)]
            )
        else:
            painter.drawPolyline(
                [QPointF(s * 0.5 - wing, y1 + wing), QPointF(s * 0.5, y1), QPointF(s * 0.5 + wing, y1 + wing)]
            )
        painter.drawLine(QPointF(s * 0.26, s * 0.84), QPointF(s * 0.74, s * 0.84))
    elif name == "transfer":
        painter.drawLine(QPointF(s * 0.2, s * 0.38), QPointF(s * 0.76, s * 0.38))
        painter.drawPolyline(
            [QPointF(s * 0.62, s * 0.26), QPointF(s * 0.78, s * 0.38), QPointF(s * 0.62, s * 0.5)]
        )
        painter.drawLine(QPointF(s * 0.8, s * 0.62), QPointF(s * 0.24, s * 0.62))
        painter.drawPolyline(
            [QPointF(s * 0.38, s * 0.5), QPointF(s * 0.22, s * 0.62), QPointF(s * 0.38, s * 0.74)]
        )
    elif name == "coins":
        painter.drawEllipse(QRectF(s * 0.22, s * 0.26, s * 0.56, s * 0.22))
        painter.drawLine(QPointF(s * 0.22, s * 0.37), QPointF(s * 0.22, s * 0.6))
        painter.drawLine(QPointF(s * 0.78, s * 0.37), QPointF(s * 0.78, s * 0.6))
        path = QPainterPath(QPointF(s * 0.22, s * 0.6))
        path.quadTo(QPointF(s * 0.5, s * 0.78), QPointF(s * 0.78, s * 0.6))
        painter.drawPath(path)
        painter.drawLine(QPointF(s * 0.22, s * 0.66), QPointF(s * 0.22, s * 0.74))
        painter.drawLine(QPointF(s * 0.78, s * 0.66), QPointF(s * 0.78, s * 0.74))
        path2 = QPainterPath(QPointF(s * 0.22, s * 0.74))
        path2.quadTo(QPointF(s * 0.5, s * 0.92), QPointF(s * 0.78, s * 0.74))
        painter.drawPath(path2)
    elif name == "calendar":
        painter.drawRoundedRect(QRectF(s * 0.16, s * 0.24, s * 0.68, s * 0.58), s * 0.1, s * 0.1)
        painter.drawLine(QPointF(s * 0.16, s * 0.42), QPointF(s * 0.84, s * 0.42))
        painter.drawLine(QPointF(s * 0.34, s * 0.16), QPointF(s * 0.34, s * 0.3))
        painter.drawLine(QPointF(s * 0.66, s * 0.16), QPointF(s * 0.66, s * 0.3))
        painter.drawPoint(QPointF(s * 0.36, s * 0.58))
        painter.drawPoint(QPointF(s * 0.5, s * 0.58))
        painter.drawPoint(QPointF(s * 0.64, s * 0.58))
    elif name == "target":
        painter.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.3, s * 0.3)
        painter.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.14, s * 0.14)


def category_icon(key: str, color: str | None = None, size: int = 18) -> QIcon:
    color = color or CATEGORY_COLORS.get(key, "#888888")
    pixmap, painter = _canvas(size)
    _draw_category(painter, key, size, color)
    painter.end()
    return QIcon(pixmap)


def finance_icon(name: str, color: str = "#5B6BD6", size: int = 18) -> QIcon:
    pixmap, painter = _canvas(size)
    _draw_icon(painter, name, size, color)
    painter.end()
    return QIcon(pixmap)


def app_nav_icon(name: str, color: str, size: int = 18) -> QIcon:
    """导航栏图标：日程用日历，记账/月报/资金用财务图标。"""
    mapping = {"schedule": "calendar", "overview": "wallet", "report": "chart", "accounts": "layers"}
    pixmap, painter = _canvas(size)
    _draw_icon(painter, mapping.get(name, name), size, color)
    painter.end()
    return QIcon(pixmap)
