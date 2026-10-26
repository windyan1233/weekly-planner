"""周视图控件（一次只显示一周，7 天时间轴）。

设计取舍
--------
* 使用「共享滚动时间轴 + 每天一列」的经典周视图：任务块按真实时间定位，
  同一天重叠的任务自动分列排布，永远不会互相覆盖。
* 顶部星期标题由 :class:`WeekView` 自己绘制，坐标直接取自下面各列的几何位置，
  因此列宽变化时标题和内容始终对齐。
* 点击空白时间段 = 以该时间快速新建计划时间；点击任务块 = 查看详情。
* 有计划结束时间的任务按真实起止时间绘制：同一天是一整块；跨天时开始那天画到
  23:00、结束那天从 07:00 开始、中间每天在 12:00 画一条细的「跨天延续」横条。
* 任务块半透明地画在课程块上面（不因为课程重叠而缩窄，靠透明度和绘制顺序区分）。
* 今天所在列有柔和底色、日期高亮，并在当前时间处画一条细指示线。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTime, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QToolTip,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .courses.models import CourseBlock
from .models import KIND_DUE, KIND_PLAN, PRIORITY_COLORS, Occurrence, priority_label
from .theme import Palette, current_palette
from .time_utils import WEEKDAY_LABELS, format_time, week_days, week_range_label, start_of_week
from .widgets import mix

HOUR_HEIGHT = 52
GUTTER_WIDTH = 56
COLUMN_GAP = 8
DAY_COUNT = 7
HEADER_HEIGHT = 66
COLUMN_PAD_X = 5
COLUMN_PAD_Y = 4
MIN_CHIP_HEIGHT = 24
SNAP_MINUTES = 15

# 跨天计划：开始那天画到 23:00，结束那天从 07:00 开始画，
# 中间每天在 12:00 位置画一条细的「跨天延续」横条。
CROSS_START_DAY_END_MINUTES = 23 * 60
CROSS_END_DAY_START_MINUTES = 7 * 60
CONTINUATION_AT_MINUTES = 12 * 60
CONTINUATION_HEIGHT = 18
CONTINUATION_GAP = 4

# 任务块约 0.78 不透明度（课程表会从下面透出来），延续横条更淡
TASK_FILL_ALPHA = 200
CONTINUATION_FILL_ALPHA = 78
CONTINUATION_BORDER_ALPHA = 140


@dataclass(frozen=True)
class DaySegment:
    """某个计划/截止项在「某一天」里要画的那一段。

    ``continuation`` 为 True 表示这是跨天计划中间某天的细横条。
    """

    occurrence: Occurrence
    start_minutes: int
    end_minutes: int
    continuation: bool = False
    day: date | None = None

    @property
    def key(self) -> tuple:
        return self.occurrence.key

    @property
    def minutes(self) -> int:
        return max(1, self.end_minutes - self.start_minutes)


def build_day_segments(occurrences: list[Occurrence], day: date) -> list[DaySegment]:
    """把出现项裁剪成「这一天需要绘制的一段」——纯函数，方便单测。"""
    segments: list[DaySegment] = []
    for occ in occurrences:
        start_day = occ.start.date()
        if occ.end_at is None:
            # 旧计划：原来的固定时长短块
            if start_day != day:
                continue
            start = occ.start.hour * 60 + occ.start.minute
            end = min(24 * 60, max(start + 1, start + occ.duration_minutes))
            segments.append(DaySegment(occ, start, end, continuation=False, day=day))
            continue

        end_day = occ.end_at.date()
        if day < start_day or day > end_day:
            continue
        end_clock = occ.end_at.hour * 60 + occ.end_at.minute

        if start_day == end_day:
            start = occ.start.hour * 60 + occ.start.minute
            segments.append(
                DaySegment(
                    occ,
                    start,
                    max(start + 1, min(24 * 60, end_clock)),
                    continuation=False,
                    day=day,
                )
            )
        elif day == start_day:
            start = occ.start.hour * 60 + occ.start.minute
            end = CROSS_START_DAY_END_MINUTES
            if start >= end:
                # 23:00 之后才开始：画到当天结束，保证还能看到并点击
                end = min(24 * 60, start + 15)
            segments.append(DaySegment(occ, start, end, continuation=False, day=day))
        elif day == end_day:
            start = CROSS_END_DAY_START_MINUTES
            if end_clock <= start:
                # 结束时间早于 07:00：当天 00:00 到结束时间才是真实占用的区间
                start = 0
            segments.append(
                DaySegment(
                    occ,
                    start,
                    max(start + 1, min(24 * 60, end_clock)),
                    continuation=False,
                    day=day,
                )
            )
        else:
            segments.append(
                DaySegment(
                    occ,
                    CONTINUATION_AT_MINUTES,
                    CONTINUATION_AT_MINUTES,
                    continuation=True,
                    day=day,
                )
            )
    segments.sort(key=lambda seg: (seg.start_minutes, seg.continuation, seg.occurrence.title))
    return segments


def assign_lane_ranges(items: list[tuple[tuple, float, float]]) -> dict[tuple, tuple[int, int]]:
    """给同一列里重叠的块分配通道，返回 {key: (lane, lane_count)}。"""
    ordered = sorted(items, key=lambda item: (item[1], item[2], str(item[0])))
    if not ordered:
        return {}

    clusters: list[list[tuple[tuple, float, float]]] = []
    cluster: list[tuple[tuple, float, float]] = []
    cluster_end = -1.0
    for item in ordered:
        _, start, end = item
        if cluster and start >= cluster_end:
            clusters.append(cluster)
            cluster = []
            cluster_end = end
        cluster.append(item)
        cluster_end = max(cluster_end, end)
    if cluster:
        clusters.append(cluster)

    result: dict[tuple, tuple[int, int]] = {}
    for group in clusters:
        lane_ends: list[float] = []
        assignments: list[tuple[tuple, int]] = []
        for key, start, end in group:
            placed = False
            for index, lane_end in enumerate(lane_ends):
                if lane_end <= start:
                    lane_ends[index] = end
                    assignments.append((key, index))
                    placed = True
                    break
            if not placed:
                lane_ends.append(end)
                assignments.append((key, len(lane_ends) - 1))
        lane_count = max(1, len(lane_ends))
        for key, lane in assignments:
            result[key] = (lane, lane_count)
    return result


def _font(size: int, weight: int = 400) -> QFont:
    font = QFont()
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


# --------------------------------------------------------------------------
# 时间轴左侧刻度
# --------------------------------------------------------------------------
class TimeGutter(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(GUTTER_WIDTH)
        self._palette = current_palette()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(_font(10, 400))
        painter.setPen(QColor(palette.text_muted))
        for hour in range(24):
            y = hour * HOUR_HEIGHT + COLUMN_PAD_Y
            if hour == 0:
                continue
            text = f"{hour:02d}:00"
            rect = QRect(0, int(y) - 14, GUTTER_WIDTH - 10, 14)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, text)
        painter.end()


# --------------------------------------------------------------------------
# 任务块
# --------------------------------------------------------------------------
class EventChip(QWidget):
    clicked = Signal(int)
    context_requested = Signal(int, QPoint)

    def __init__(
        self,
        segment: "DaySegment | Occurrence",
        palette: Palette,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if isinstance(segment, Occurrence):
            # 兼容直接传 Occurrence 的老用法（按整天未裁剪的一段处理）
            start = segment.start.hour * 60 + segment.start.minute
            segment = DaySegment(
                segment, start, start + segment.duration_minutes, False, segment.start.date()
            )
        self._segment = segment
        self._occ = segment.occurrence
        self._palette = palette
        self._now = now
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setToolTip(self._tooltip())
        self._font_time = _font(10, 400)
        self._font_title = _font(12, 600)
        self._font_small = _font(10, 500)
        self._font_tiny = _font(9, 600)

    # ------------------------------------------------------------------
    @property
    def occurrence(self) -> Occurrence:
        return self._occ

    @property
    def segment(self) -> DaySegment:
        return self._segment

    @property
    def is_continuation(self) -> bool:
        return self._segment.continuation

    def set_now(self, now: datetime) -> None:
        self._now = now
        self.update()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def _tooltip(self) -> str:
        occ = self._occ
        task = occ.task
        if self.is_continuation:
            lines = [f"{task.title} · 跨天延续", occ.detail_text]
        else:
            lines = [f"{task.title}", occ.detail_text]
        if task.description:
            lines.append(task.description)
        if task.notes:
            lines.append(f"备注：{task.notes}")
        lines.append(f"分类：{task.category} · 优先级：{priority_label(task.priority)}")
        if task.plans and len(task.plans) > 1:
            lines.append("")
            lines.append(task.group_hint())
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def _colors(self) -> tuple[QColor, QColor, QColor]:
        palette = self._palette
        occ = self._occ
        if occ.is_done or occ.task.status == "done":
            return (
                QColor(palette.surface_alt),
                QColor(palette.border),
                QColor(palette.done_text),
            )
        if occ.kind == KIND_DUE:
            base = QColor(palette.danger if occ.task.is_overdue(self._now) else palette.warning)
        else:
            base = QColor(PRIORITY_COLORS.get(occ.task.priority, palette.accent))
        fill = mix(palette.surface, base.name(), 0.16 if palette.name == "light" else 0.22)
        border = mix(palette.surface, base.name(), 0.42)
        return fill, border, base

    def _time_text(self) -> str:
        occ = self._occ
        if occ.kind == KIND_DUE:
            return "截止 " + format_time(occ.start)
        plan = occ.plan
        if plan is not None and plan.end_at is not None:
            if occ.is_cross_day:
                if self._segment.day == occ.start.date():
                    return format_time(occ.start) + " · 跨天"
                if self._segment.day == occ.end_at.date():
                    return "→ " + format_time(occ.end_at)
                return "跨天"
            return f"{format_time(occ.start)}-{format_time(plan.end_at)}"
        return format_time(occ.start)

    def paintEvent(self, event) -> None:  # noqa: N802
        if self.is_continuation:
            self._paint_continuation()
            return
        palette = self._palette
        occ = self._occ
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fill, border, accent = self._colors()
        height = self.height()

        # 背景：半透明，课程块会从下面透出来（任务永远画在课程上面）
        if occ.is_done:
            fill = QColor(palette.surface_alt)
        if self._hover:
            fill = mix(fill.name(), palette.accent, 0.10)
        fill = QColor(fill)
        fill.setAlpha(TASK_FILL_ALPHA)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        painter.fillPath(path, fill)
        pen = QPen(border, 1.0)
        if occ.kind == KIND_DUE:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([3, 2])
        painter.setPen(pen)
        painter.drawPath(path)

        # 左侧强调条
        bar = QRectF(rect.left() + 2, rect.top() + 5, 3, max(6.0, rect.height() - 10))
        bar_path = QPainterPath()
        bar_path.addRoundedRect(bar, 1.5, 1.5)
        if occ.is_done:
            painter.fillPath(bar_path, QColor(palette.border_strong))
        else:
            painter.fillPath(bar_path, accent)

        pad_left = 11
        content_width = int(rect.width()) - pad_left - 8
        compact = height < 34
        badge = self._badge_text(compact)
        badge_width = 0
        badge_font = self._font_tiny if compact else self._font_small
        if badge:
            painter.setFont(badge_font)
            badge_width = QFontMetrics(badge_font).horizontalAdvance(badge) + 10

        text_color = QColor(palette.done_text if occ.is_done else palette.text)
        time_text = self._time_text()

        if compact:
            # 单行紧凑显示。时间轴本身已经表达了时刻，所以很窄的块只显示任务名，
            # 避免出现「0...」这种没有信息量的省略。
            painter.setFont(self._font_small)
            metrics = QFontMetrics(self._font_small)
            available = max(10, content_width - badge_width - 4)
            narrow = content_width < 78
            time_part = format_time(occ.start) + " "
            time_width = 0 if narrow else metrics.horizontalAdvance(time_part)
            if not narrow:
                painter.setPen(QColor(palette.done_text if occ.is_done else palette.text_muted))
                painter.drawText(
                    QRect(pad_left, 0, time_width, height),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    time_part,
                )
            title_font = QFont(self._font_small)
            if occ.is_done:
                title_font.setStrikeOut(True)
            painter.setFont(title_font)
            painter.setPen(text_color)
            title_width = max(10, available - time_width)
            painter.drawText(
                QRect(pad_left + time_width, 0, title_width, height),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                QFontMetrics(title_font).elidedText(occ.title, Qt.TextElideMode.ElideRight, title_width),
            )
            if badge and not narrow:
                self._draw_badge(
                    painter,
                    badge,
                    QRect(pad_left + content_width - badge_width, 0, badge_width, height),
                    compact=True,
                )
            painter.end()
            return

        # 第一行：时间（有结束时间时显示 HH:mm-HH:mm）
        painter.setFont(self._font_time)
        painter.setPen(QColor(palette.text_muted if not occ.is_done else palette.done_text))
        time_rect = QRect(pad_left, 4, content_width - badge_width - 4, 14)
        painter.drawText(
            time_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(self._font_time).elidedText(
                time_text + (" · 计划" if occ.kind == KIND_PLAN and occ.plan_total > 1 else ""),
                Qt.TextElideMode.ElideRight,
                time_rect.width(),
            ),
        )
        if badge:
            self._draw_badge(painter, badge, QRect(pad_left + content_width - badge_width, 4, badge_width, 14))

        # 第二行：任务名称
        title_font = QFont(self._font_title)
        if occ.is_done:
            title_font.setStrikeOut(True)
        painter.setFont(title_font)
        painter.setPen(text_color)
        title_rect = QRect(pad_left, 18, content_width, 18)
        metrics = QFontMetrics(title_font)
        if height >= 58:
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(occ.title, Qt.TextElideMode.ElideRight, title_rect.width()),
            )
            # 第三行：说明 / 分类
            detail = occ.plan.label if (occ.kind == KIND_PLAN and occ.plan and occ.plan.label) else occ.task.category
            painter.setFont(self._font_small)
            painter.setPen(QColor(palette.done_text if occ.is_done else palette.text_muted))
            painter.drawText(
                QRect(pad_left, 36, content_width, 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(self._font_small).elidedText(detail, Qt.TextElideMode.ElideRight, content_width),
            )
        else:
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(occ.title, Qt.TextElideMode.ElideRight, title_rect.width()),
            )
        painter.end()

    def _paint_continuation(self) -> None:
        """跨天计划中间某天的细横条：低透明度、带任务名、可点击。"""
        palette = self._palette
        occ = self._occ
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        _, border, accent = self._colors()
        fill = QColor(accent)
        fill.setAlpha(CONTINUATION_FILL_ALPHA)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.fillPath(path, fill)
        line = QColor(border)
        line.setAlpha(CONTINUATION_BORDER_ALPHA)
        painter.setPen(QPen(line, 1.0))
        painter.drawPath(path)

        text_color = QColor(palette.done_text if occ.is_done else palette.text_secondary)
        painter.setPen(text_color)
        painter.setFont(self._font_tiny)
        metrics = QFontMetrics(self._font_tiny)
        text_rect = QRect(9, 0, max(10, int(rect.width()) - 90), int(rect.height()))
        title = metrics.elidedText(occ.title, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            title,
        )
        tag = "跨天延续"
        tag_rect = QRect(max(10, int(rect.width()) - 78), 0, 70, int(rect.height()))
        painter.setPen(QColor(palette.text_muted))
        painter.drawText(
            tag_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            tag,
        )
        painter.end()

    def _badge_text(self, compact: bool = False) -> str:
        occ = self._occ
        done = occ.is_done or occ.task.status == "done"
        if compact:
            if done:
                return "✓"
            if occ.kind == KIND_DUE:
                return "逾" if occ.task.is_overdue(self._now) else "截"
            if occ.is_cross_day:
                return "跨"
            return ""
        if done:
            return "已完成"
        if occ.plan_total > 1 and occ.kind == KIND_PLAN:
            return f"{occ.plan_index}/{occ.plan_total}"
        if occ.kind == KIND_DUE:
            return "逾期" if occ.task.is_overdue(self._now) else "截止"
        if occ.is_cross_day:
            return "跨天"
        return ""

    def _draw_badge(self, painter: QPainter, text: str, rect: QRect, compact: bool = False) -> None:
        palette = self._palette
        occ = self._occ
        painter.setFont(self._font_tiny if compact else self._font_small)
        if occ.is_done or occ.task.status == "done":
            color = QColor(palette.success)
            background = QColor(palette.success_soft)
        elif occ.kind == KIND_DUE:
            color = QColor(palette.danger if occ.task.is_overdue(self._now) else palette.warning)
            background = QColor(palette.danger_soft if occ.task.is_overdue(self._now) else palette.warning_soft)
        else:
            color = QColor(palette.text_secondary)
            background = QColor(palette.today_bg)
        pill_height = 13 if compact else 15
        offset = max(0, (rect.height() - pill_height) / 2)
        pill = QRectF(rect).adjusted(0, offset, 0, -offset)
        path = QPainterPath()
        path.addRoundedRect(pill, 5, 5)
        painter.fillPath(path, background)
        painter.setPen(color)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._occ.task_id)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(self._occ.task_id, event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)


# --------------------------------------------------------------------------
# 一天的列
# --------------------------------------------------------------------------
def assign_lanes(occurrences: list[Occurrence]) -> dict[tuple, tuple[int, int]]:
    """给重叠的事件分配通道，返回 {事件 key: (lane, lane_count)}。

    仅用于「同一天、未裁剪」的事件；列内实际布局使用 :func:`assign_lane_ranges`
    按真实绘制片段计算，跨天计划不会因为原始时长过长而把整列挤窄。
    """
    items: list[tuple[tuple, float, float]] = []
    for occ in occurrences:
        start = float(occ.start.hour * 60 + occ.start.minute)
        items.append((occ.key, start, start + float(occ.duration_minutes)))
    return assign_lane_ranges(items)


class DayColumn(QWidget):
    slot_clicked = Signal(object, object)  # date, QTime
    chip_clicked = Signal(int)
    chip_context_requested = Signal(int, QPoint)
    course_clicked = Signal(object)  # CourseBlock

    def __init__(self, day: date, palette: Palette, now: datetime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._day = day
        self._palette = palette
        self._now = now
        self._is_today = day == now.date()
        self._occurrences: list[Occurrence] = []
        self._segments: list[DaySegment] = []
        self._course_blocks: list[CourseBlock] = []
        self._chips: dict[tuple, EventChip] = {}
        self._lanes: dict[tuple, tuple[int, int]] = {}
        self._continuation_index: dict[tuple, int] = {}
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover_minute: int | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(24 * HOUR_HEIGHT)
        self.setMinimumWidth(60)

    # ------------------------------------------------------------------
    def day(self) -> date:
        return self._day

    def set_day(self, day: date, now: datetime) -> None:
        self._day = day
        self._now = now
        self._is_today = day == now.date()
        self.update()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        for chip in self._chips.values():
            chip.set_palette(palette)
        self.update()

    def set_now(self, now: datetime) -> None:
        old_today = self._is_today
        self._now = now
        self._is_today = self._day == now.date()
        for chip in self._chips.values():
            chip.set_now(now)
        if old_today != self._is_today:
            self.update()
        else:
            self.update()

    def set_occurrences(self, occurrences: list[Occurrence]) -> None:
        self._occurrences = occurrences
        for chip in self._chips.values():
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        self._segments = build_day_segments(occurrences, self._day)
        block_ranges = [
            (seg.key, float(seg.start_minutes), float(seg.end_minutes))
            for seg in self._segments
            if not seg.continuation
        ]
        self._lanes = assign_lane_ranges(block_ranges)
        self._continuation_index = {}
        next_index = 0
        for seg in self._segments:
            if not seg.continuation:
                continue
            self._continuation_index[seg.key] = next_index
            next_index += 1
        for seg in self._segments:
            chip = EventChip(seg, self._palette, self._now, self)
            chip.clicked.connect(self.chip_clicked)
            chip.context_requested.connect(self.chip_context_requested)
            chip.show()
            self._chips[seg.key] = chip
        self._layout_chips()

    def occurrences(self) -> list[Occurrence]:
        return list(self._occurrences)

    def segments(self) -> list[DaySegment]:
        return list(self._segments)

    # -- 课程表 --------------------------------------------------------
    def set_course_blocks(self, blocks: list[CourseBlock]) -> None:
        self._course_blocks = list(blocks)
        self.update()

    def _course_rect(self, block: CourseBlock) -> QRectF:
        width = max(10, self.width() - 2 * COLUMN_PAD_X)
        top = COLUMN_PAD_Y + block.start_minutes / 60 * HOUR_HEIGHT
        height = max(16.0, (block.end_minutes - block.start_minutes) / 60 * HOUR_HEIGHT - 2)
        return QRectF(COLUMN_PAD_X, top, width, height)

    def _course_at(self, position) -> CourseBlock | None:
        for block in self._course_blocks:
            if self._course_rect(block).contains(QPointF(position)):
                return block
        return None

    # ------------------------------------------------------------------
    def _layout_chips(self) -> None:
        if not self._chips or not self._segments:
            return
        width = max(10, self.width() - 2 * COLUMN_PAD_X)
        for seg in self._segments:
            chip = self._chips.get(seg.key)
            if chip is None:
                continue
            if seg.continuation:
                # 「跨天延续」横条：整行宽度、约 12:00 位置，多条时往下错开
                offset = self._continuation_index.get(seg.key, 0) * (
                    CONTINUATION_HEIGHT + CONTINUATION_GAP
                )
                top = COLUMN_PAD_Y + int(CONTINUATION_AT_MINUTES / 60 * HOUR_HEIGHT) + offset
                chip.setGeometry(COLUMN_PAD_X, top, max(24, width), CONTINUATION_HEIGHT)
                continue
            lane, lane_count = self._lanes.get(seg.key, (0, 1))
            lane_width = width / lane_count
            gap = 3 if lane_count > 1 else 0
            x = COLUMN_PAD_X + int(lane * lane_width)
            chip_width = max(16 if lane_count > 1 else 24, int(lane_width) - gap)
            top = COLUMN_PAD_Y + int(seg.start_minutes / 60 * HOUR_HEIGHT)
            height = max(MIN_CHIP_HEIGHT, int(seg.minutes / 60 * HOUR_HEIGHT) - 2)
            if seg.end_minutes >= 24 * 60:
                height = max(MIN_CHIP_HEIGHT, self.height() - COLUMN_PAD_Y - top)
            chip.setGeometry(x, top, chip_width, height)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_chips()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        palette = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        background = QColor(palette.today_bg if self._is_today else palette.surface)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        painter.fillPath(path, background)
        painter.setPen(QPen(QColor(palette.today_border if self._is_today else palette.border), 1.4 if self._is_today else 1.0))
        painter.drawPath(path)

        # 小时分隔线
        painter.save()
        painter.setClipPath(path)
        painter.setPen(QPen(QColor(palette.grid_line), 1.0))
        for hour in range(1, 24):
            y = COLUMN_PAD_Y + hour * HOUR_HEIGHT
            painter.drawLine(QPointF(rect.left() + 8, y), QPointF(rect.right() - 8, y))
        # 周末淡淡的底纹
        if self._day.weekday() >= 5:
            painter.fillPath(path, QColor(0, 0, 0, 6) if palette.name == "light" else QColor(255, 255, 255, 5))
        painter.restore()

        # 课程表（背景层，任务块会画在上面）
        for block in self._course_blocks:
            rect = self._course_rect(block)
            base = QColor(block.color)
            fill = QColor(base)
            fill.setAlpha(36 if palette.name == "light" else 48)
            painter.save()
            painter.setClipPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 7, 7)
            painter.setBrush(base)
            painter.drawRoundedRect(
                QRectF(rect.left(), rect.top() + 2, 3.5, max(4.0, rect.height() - 4)), 1.8, 1.8
            )
            if rect.height() >= 20:
                font = QFont()
                font.setPixelSize(10)
                font.setWeight(QFont.Weight.DemiBold)
                painter.setFont(font)
                painter.setPen(QColor(palette.text))
                text_rect = rect.adjusted(8, 3, -4, -2)
                metrics = QFontMetrics(font)
                name = metrics.elidedText(
                    block.name, Qt.TextElideMode.ElideRight, max(10, int(text_rect.width()))
                )
                painter.drawText(
                    text_rect,
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                    name,
                )
                if rect.height() >= 38 and (block.location or block.teacher):
                    small = QFont()
                    small.setPixelSize(9)
                    painter.setFont(small)
                    painter.setPen(QColor(palette.text_secondary))
                    detail = block.location or block.teacher
                    painter.drawText(
                        text_rect.adjusted(0, 14, 0, 0),
                        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                        QFontMetrics(small).elidedText(
                            detail, Qt.TextElideMode.ElideRight, max(10, int(text_rect.width()))
                        ),
                    )
            painter.restore()

        # 当前时间指示线
        if self._is_today:
            minute_of_day = self._now.hour * 60 + self._now.minute + self._now.second / 60
            y = COLUMN_PAD_Y + minute_of_day / 60 * HOUR_HEIGHT
            line_color = QColor(palette.accent)
            painter.setPen(QPen(line_color, 1.6))
            painter.drawLine(QPointF(rect.left() + 6, y), QPointF(rect.right() - 4, y))
            painter.setBrush(line_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(rect.left() + 6, y), 3.0, 3.0)

        # 空白处的「点击添加」提示
        if self._hover_minute is not None and not self._chips:
            y = COLUMN_PAD_Y + self._hover_minute / 60 * HOUR_HEIGHT
            painter.setPen(QPen(QColor(palette.accent), 1.0, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(rect.left() + 8, y), QPointF(rect.right() - 8, y))
        painter.end()

    # ------------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        block = self._course_at(event.position())
        if block is not None:
            QToolTip.showText(event.globalPosition().toPoint(), block.tooltip, self)
        minute = self._minute_at(event.position().y())
        if minute != self._hover_minute:
            self._hover_minute = minute
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_minute = None
        self.update()
        super().leaveEvent(event)

    def _minute_at(self, y: float) -> int:
        raw = (y - COLUMN_PAD_Y) / HOUR_HEIGHT * 60
        snapped = int(round(raw / SNAP_MINUTES)) * SNAP_MINUTES
        return max(0, min(24 * 60 - 1, snapped))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            block = self._course_at(event.position())
            if block is not None:
                self.course_clicked.emit(block)
                event.accept()
                return
            minute = self._minute_at(event.position().y())
            self.slot_clicked.emit(self._day, QTime(minute // 60, minute % 60))
            event.accept()
            return
        super().mousePressEvent(event)


# DayColumn 上挂两个信号（在类外部定义以保持类定义简洁）
DayColumn.chip_clicked = Signal(int)
DayColumn.chip_context_requested = Signal(int, QPoint)


class WeekBody(QWidget):
    def __init__(self, palette: Palette, now: datetime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._gutter = TimeGutter(self)
        self._columns: list[DayColumn] = []
        days = week_days(now)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(COLUMN_GAP)
        layout.addWidget(self._gutter)
        for day in days:
            column = DayColumn(day, palette, now, self)
            self._columns.append(column)
            layout.addWidget(column, 1)
        self.setFixedHeight(24 * HOUR_HEIGHT + 2 * COLUMN_PAD_Y)

    @property
    def columns(self) -> list[DayColumn]:
        return self._columns

    def set_course_blocks(self, blocks: list[CourseBlock]) -> None:
        grouped: dict[date, list[CourseBlock]] = {column.day(): [] for column in self._columns}
        for block in blocks:
            if block.day in grouped:
                grouped[block.day].append(block)
        for column in self._columns:
            column.set_course_blocks(grouped.get(column.day(), []))

    def set_palette(self, palette: Palette) -> None:
        self._gutter.set_palette(palette)
        for column in self._columns:
            column.set_palette(palette)

    def set_days(self, days: list[date], now: datetime) -> None:
        for column, day in zip(self._columns, days):
            column.set_day(day, now)


# --------------------------------------------------------------------------
# 周视图
# --------------------------------------------------------------------------
class WeekView(QWidget):
    task_clicked = Signal(int)
    task_context_requested = Signal(int, QPoint)
    slot_clicked = Signal(object, object)     # date, QTime
    add_requested = Signal(object)            # date
    week_changed = Signal(object)             # date (week start)
    course_clicked = Signal(object)           # CourseBlock

    def __init__(self, palette: Palette | None = None, now: datetime | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette or current_palette()
        self._now = now or datetime.now()
        self._week_start = start_of_week(self._now)
        self._occurrences: list[Occurrence] = []
        self._hover_column: int | None = None
        self._scroll_ready = False
        self.setObjectName("WeekView")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addSpacing(HEADER_HEIGHT)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._body = WeekBody(self._palette, self._now, self._scroll)
        self._scroll.setWidget(self._body)
        layout.addWidget(self._scroll, 1)

        for column in self._body.columns:
            column.slot_clicked.connect(self.slot_clicked)
            column.chip_clicked.connect(self.task_clicked)
            column.chip_context_requested.connect(self.task_context_requested)
            column.course_clicked.connect(self.course_clicked)

    # ------------------------------------------------------------------
    def theme_palette(self) -> Palette:
        return self._palette

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._body.set_palette(palette)
        self.update()

    def week_start(self) -> date:
        return self._week_start

    def week_end(self) -> date:
        return self._week_start + timedelta(days=6)

    def columns(self) -> list[DayColumn]:
        return self._body.columns

    def visible_week_label(self) -> str:
        return week_range_label(self._week_start, self.week_end())

    # ------------------------------------------------------------------
    def set_week(self, any_day: date | datetime) -> None:
        new_start = start_of_week(any_day)
        changed = new_start != self._week_start
        self._week_start = new_start
        days = week_days(new_start)
        self._body.set_days(days, self._now)
        self._distribute()
        if changed:
            self.week_changed.emit(new_start)
            QTimer.singleShot(0, self.scroll_to_default)
        self.update()

    def set_now(self, now: datetime, *, scroll_if_today: bool = False) -> None:
        previous_day = self._now.date()
        self._now = now
        for column in self._body.columns:
            column.set_now(now)
        if scroll_if_today and now.date() != previous_day and now.date() == self._week_start and self._scroll_ready:
            QTimer.singleShot(0, self.scroll_to_now)
        self.update()

    def now(self) -> datetime:
        return self._now

    def set_occurrences(self, occurrences: list[Occurrence]) -> None:
        self._occurrences = list(occurrences)
        self._distribute()

    def set_course_blocks(self, blocks: list[CourseBlock]) -> None:
        self._body.set_course_blocks(blocks)
        self.update()

    def _distribute(self) -> None:
        grouped: dict[date, list[Occurrence]] = {day: [] for day in week_days(self._week_start)}
        for occ in self._occurrences:
            # 跨天计划会出现在它覆盖的每一天：开始日、结束日、以及中间的延续日；
            # 只画本周内的部分。
            for day in occ.covered_dates():
                if day in grouped:
                    grouped[day].append(occ)
        for column in self._body.columns:
            column.set_occurrences(grouped.get(column.day(), []))

    # ------------------------------------------------------------------
    def scroll_to_now(self) -> None:
        if not (self._week_start <= self._now.date() <= self.week_end()):
            self.scroll_to_hour(8)
            return
        minutes = self._now.hour * 60 + self._now.minute
        target = int(minutes / 60 * HOUR_HEIGHT) - self._scroll.viewport().height() // 3
        self._scroll.verticalScrollBar().setValue(max(0, target))
        self._scroll_ready = True

    def scroll_to_hour(self, hour: int) -> None:
        self._scroll.verticalScrollBar().setValue(max(0, hour * HOUR_HEIGHT - 8))
        self._scroll_ready = True

    def scroll_to_default(self) -> None:
        if self._week_start <= self._now.date() <= self.week_end():
            self.scroll_to_now()
        else:
            self.scroll_to_hour(8)
        self._scroll_ready = True

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._scroll_ready:
            QTimer.singleShot(0, self.scroll_to_default)

    # ------------------------------------------------------------------
    def _column_geometries(self) -> list[QRect]:
        rects: list[QRect] = []
        for column in self._body.columns:
            top_left = column.mapTo(self, QPoint(0, 0))
            rects.append(QRect(top_left.x(), 2, column.width(), HEADER_HEIGHT - 8))
        return rects

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        days = week_days(self._week_start)
        today = self._now.date()
        rects = self._column_geometries()

        for index, (day, rect) in enumerate(zip(days, rects)):
            is_today = day == today
            hovered = self._hover_column == index
            cell = rect.adjusted(-3, 0, 3, 0)
            if is_today:
                background = QColor(palette.today_bg)
                background.setAlpha(150)
            elif hovered:
                background = QColor(palette.surface_hover)
            else:
                background = None
            if background is not None:
                path = QPainterPath()
                path.addRoundedRect(QRectF(cell), 12, 12)
                painter.fillPath(path, background)

            weekday_rect = QRect(cell.left(), cell.top() + 8, cell.width(), 16)
            painter.setFont(_font(11, 500 if not is_today else 600))
            painter.setPen(QColor(palette.accent if is_today else palette.text_muted))
            weekday_text = WEEKDAY_LABELS[day.weekday()]
            painter.drawText(weekday_rect, Qt.AlignmentFlag.AlignCenter, weekday_text)

            number_rect = QRect(cell.left(), cell.top() + 26, cell.width(), 28)
            painter.setFont(_font(19, 600 if is_today else 500))
            text = f"{day.day}"
            if is_today:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.accent))
                pill = QRectF(number_rect.center().x() - 16, number_rect.top() + 1, 32, 26)
                path = QPainterPath()
                path.addRoundedRect(pill, 13, 13)
                painter.fillPath(path, QColor(palette.accent))
                painter.setPen(QColor(palette.on_accent))
                painter.drawText(number_rect, Qt.AlignmentFlag.AlignCenter, text)
            else:
                painter.setPen(QColor(palette.text if day.weekday() < 5 else palette.text_secondary))
                painter.drawText(number_rect, Qt.AlignmentFlag.AlignCenter, text)
                if day.day == 1:
                    painter.setFont(_font(9, 500))
                    painter.setPen(QColor(palette.text_muted))
                    painter.drawText(
                        QRect(cell.left(), cell.top() + 52, cell.width(), 12),
                        Qt.AlignmentFlag.AlignCenter,
                        f"{day.month} 月",
                    )
            if hovered:
                painter.setFont(_font(11, 500))
                painter.setPen(QColor(palette.accent))
                painter.drawText(
                    QRect(cell.right() - 22, cell.top() + 8, 18, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    "+",
                )
        painter.end()

    # ------------------------------------------------------------------
    def _column_index_at(self, pos: QPoint) -> int | None:
        for index, rect in enumerate(self._column_geometries()):
            if rect.adjusted(-4, 0, 4, 4).contains(pos):
                return index
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < HEADER_HEIGHT:
            index = self._column_index_at(event.position().toPoint())
            if index is not None:
                self.add_requested.emit(week_days(self._week_start)[index])
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = None
        if event.position().y() < HEADER_HEIGHT:
            index = self._column_index_at(event.position().toPoint())
        if index != self._hover_column:
            self._hover_column = index
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if index is not None else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_column is not None:
            self._hover_column = None
            self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._body.updateGeometry()
