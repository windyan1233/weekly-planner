"""日期 / 时间工具。

约定
----
* 数据库中以「本地墙上时间」保存，格式 ``YYYY-MM-DD HH:MM``。用户在 18:00
  设定截止时间，就永远是本地 18:00，不随夏令时漂移。
* 需要做「绝对时长」计算时（例如截止前 24 小时），先把这一墙上时间按本地
  时区附加 tzinfo，再做绝对时间运算，最后转回本地墙上时间。这样在夏令时切换
  的日期也能得到正确的提醒时刻。
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, tzinfo as _TzInfo

DT_FORMAT = "%Y-%m-%d %H:%M"
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"

WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEKDAY_SHORT = ("一", "二", "三", "四", "五", "六", "日")

MODE_BEFORE_DUE_24H = "before_due_24h"
MODE_PREVIOUS_DAY_AT = "previous_day_at"

REMINDER_MODE_LABELS = {
    MODE_BEFORE_DUE_24H: "截止时间前 24 小时",
    MODE_PREVIOUS_DAY_AT: "截止日期前一天的指定时间",
}


# --------------------------------------------------------------------------
# 当前时间
# --------------------------------------------------------------------------
def now() -> datetime:
    """当前本地时间（精确到秒，符合 Windows 系统时钟）。"""
    return datetime.now()


def today() -> date:
    return date.today()


def start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min)


def end_of_day(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59))


# --------------------------------------------------------------------------
# 序列化
# --------------------------------------------------------------------------
def parse_dt(value: str | datetime | None) -> datetime | None:
    """解析数据库/CSV 里的时间字符串，兼容 ISO 的 ``T`` 分隔符。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    for fmt in (DT_FORMAT, "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # 允许带秒的 ISO 字符串
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError as exc:  # pragma: no cover - 防御性
        raise ValueError(f"无法解析时间：{value!r}") from exc


def format_dt(value: datetime) -> str:
    return value.strftime(DT_FORMAT)


def format_date(value: date) -> str:
    return value.strftime(DATE_FORMAT)


def format_time(value: datetime | time) -> str:
    return value.strftime(TIME_FORMAT)


def parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    return datetime.strptime(str(value).strip(), TIME_FORMAT).time()


# --------------------------------------------------------------------------
# 周 / 月
# --------------------------------------------------------------------------
def start_of_week(day: date | datetime) -> date:
    """所在自然周的周一。"""
    if isinstance(day, datetime):
        day = day.date()
    return day - timedelta(days=day.weekday())


def week_bounds(day: date | datetime) -> tuple[date, date]:
    """返回 (周一, 周日)。"""
    monday = start_of_week(day)
    return monday, monday + timedelta(days=6)


def week_days(day: date | datetime) -> list[date]:
    monday = start_of_week(day)
    return [monday + timedelta(days=i) for i in range(7)]


def shift_week(day: date | datetime, weeks: int) -> date:
    """平移若干周，返回那一周的周一。"""
    return start_of_week(day) + timedelta(weeks=weeks)


def week_number(day: date | datetime) -> int:
    if isinstance(day, datetime):
        day = day.date()
    return day.isocalendar().week


def month_label(day: date | datetime) -> str:
    if isinstance(day, datetime):
        day = day.date()
    return f"{day.year} 年 {day.month} 月"


def month_abbr(day: date | datetime) -> str:
    if isinstance(day, datetime):
        day = day.date()
    return f"{day.month} 月"


def week_range_label(week_start: date, week_end: date) -> str:
    if week_start.year != week_end.year:
        return f"{week_start.year}年{week_start.month}月{week_start.day}日 – {week_end.year}年{week_end.month}月{week_end.day}日"
    if week_start.month != week_end.month:
        return f"{week_start.month}月{week_start.day}日 – {week_end.month}月{week_end.day}日"
    return f"{week_start.month}月{week_start.day}日 – {week_end.day}日"


def weekday_label(day: date | datetime) -> str:
    if isinstance(day, datetime):
        day = day.date()
    return WEEKDAY_LABELS[day.weekday()]


def full_date_label(day: date | datetime) -> str:
    if isinstance(day, datetime):
        day = day.date()
    return f"{day.month}月{day.day}日 {WEEKDAY_LABELS[day.weekday()]}"


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


# --------------------------------------------------------------------------
# 时区 / 夏令时安全运算
# --------------------------------------------------------------------------
def local_tz() -> _TzInfo:
    """当前本地时区（带 DST 规则，来自系统）。"""
    return datetime.now().astimezone().tzinfo


def as_aware(value: datetime, tz: _TzInfo | None = None) -> datetime:
    """把墙上时间解释为本地时间（或指定时区）。"""
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=tz) if tz is not None else value.astimezone()


def to_local_wall(aware: datetime, tz: _TzInfo | None = None) -> datetime:
    """把带时区的时间转换回本地（或指定时区）墙上时间。"""
    if tz is not None:
        return aware.astimezone(tz).replace(tzinfo=None)
    return aware.astimezone().replace(tzinfo=None)


def shift_minutes(value: datetime, minutes: float, tz: _TzInfo | None = None) -> datetime:
    """按绝对时长平移，返回墙上时间（夏令时安全）。

    注意：``datetime + timedelta`` 在带 tzinfo 时是「墙上时间」运算，遇到夏令时
    切换会差一小时。这里先换算到 UTC 做绝对运算，再换回本地时间。
    """
    from datetime import timezone

    aware = as_aware(value, tz)
    result = aware.astimezone(timezone.utc) + timedelta(minutes=minutes)
    return to_local_wall(result, tz)


def subtract_hours(value: datetime, hours: float, tz: _TzInfo | None = None) -> datetime:
    return shift_minutes(value, -hours * 60, tz)


def due_reminder_time(
    due_at: datetime,
    mode: str = MODE_BEFORE_DUE_24H,
    previous_day_time: str | time = "09:00",
    tz: _TzInfo | None = None,
) -> datetime | None:
    """按设置计算截止提醒时刻。

    * ``before_due_24h``：截止时刻前 24 小时（绝对时长，夏令时安全）。
    * ``previous_day_at``：截止日期前一天的指定时间（默认 09:00）。
    """
    if mode == MODE_PREVIOUS_DAY_AT:
        clock = parse_time(previous_day_time)
        prev_day = due_at.date() - timedelta(days=1)
        return datetime.combine(prev_day, clock)
    return subtract_hours(due_at, 24, tz)


# --------------------------------------------------------------------------
# 可读化
# --------------------------------------------------------------------------
def humanize_delta(delta: timedelta) -> str:
    """把时长转成「2 天 3 小时」这样的中文，去掉 0 值。"""
    total = int(delta.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes and not days:
        parts.append(f"{minutes} 分钟")
    if not parts:
        parts.append("不到 1 分钟")
    return sign + " ".join(parts)


def remaining_label(target: datetime, reference: datetime | None = None) -> str:
    """「还剩 1 天」/「已逾期 2 小时」。"""
    ref = reference or now()
    delta = target - ref
    if delta.total_seconds() >= 0:
        return f"还剩 {humanize_delta(delta)}"
    return f"已逾期 {humanize_delta(-delta)}"


def clamp_datetime(value: datetime, low: datetime, high: datetime) -> datetime:
    return max(low, min(high, value))


def month_day_label(value: datetime | date) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return f"{value.month}月{value.day}日"


# --------------------------------------------------------------------------
# 计划时间（开始 / 结束）
# --------------------------------------------------------------------------
def plan_range_label(start: datetime, end: datetime | None = None) -> str:
    """计划时间的显示文本（列表与任务描述共用）。

    * 没有结束时间（旧数据）：``HH:mm``，保持原来的短格式；
    * 同一天：``HH:mm-HH:mm``；
    * 跨天：``MM-dd HH:mm → MM-dd HH:mm · 跨N天``（N = 覆盖的自然日天数）。
    """
    if end is None:
        return start.strftime(TIME_FORMAT)
    if end.date() == start.date():
        return f"{start.strftime(TIME_FORMAT)}-{end.strftime(TIME_FORMAT)}"
    span = (end.date() - start.date()).days + 1
    return (
        f"{start.strftime('%m-%d %H:%M')} → "
        f"{end.strftime('%m-%d %H:%M')} · 跨{span}天"
    )


def covered_dates(start: datetime, end: datetime | None = None) -> list[date]:
    """一个计划时间覆盖到的所有自然日（含开始与结束当天）。"""
    if end is None or end.date() <= start.date():
        return [start.date()]
    return [start.date() + timedelta(days=offset) for offset in range((end.date() - start.date()).days + 1)]
