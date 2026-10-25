"""解析教务系统导出的课表（.xls/.xlsx 转成的二维文本）。

这个格式（沈阳药科大学综合教学管理平台）的结构：

    标题行 / 学年学期信息 / 星期一…星期日
    第一大节 (01,02) 08:30-10:05 | 单元格 | …
    ...
    底部说明行

每个单元格里可能有多门课，用空行分隔；每门课 4–5 行：

    课程名
    (可选) 班级/方向说明，例如 (匹克球)
    教师
    周次([周])[节次]          例如 3-4,7-17([周])[01-02节]
    地点
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

WEEKDAY_NAMES = {
    "星期一": 0,
    "星期一": 0,
    "周一": 0,
    "星期二": 1,
    "周二": 1,
    "星期三": 2,
    "周三": 2,
    "星期四": 3,
    "周四": 3,
    "星期五": 4,
    "周五": 4,
    "星期六": 5,
    "周六": 5,
    "星期日": 6,
    "星期天": 6,
    "周日": 6,
    "周天": 6,
}

_WEEKDAYS_LABEL = ("一", "二", "三", "四", "五", "六", "日")

_TIME_RE = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})\s*[-–~]\s*(\d{1,2})\s*[:：]\s*(\d{2})")
_PERIODS_RE = re.compile(r"[\(（]\s*(\d{1,2})\s*[,，、]\s*(\d{1,2})\s*[\)）]")
_PERIODS_ALT_RE = re.compile(r"第\s*(\d{1,2})\s*[-–－~]\s*(\d{1,2})\s*节")
_BIG_SECTION_RE = re.compile(r"第([一二三四五六七八九十]+)大节")
_SCHEDULE_RE = re.compile(
    r"^(?P<weeks>[^()（）\[\]]+?)\s*[\(（]?\s*\[?\s*周\s*\]?\s*[\)）]?\s*"
    r"\[(?P<periods>[0-9\-－,，]+)\s*节?\]\s*节?$"
)
_WEEK_ONLY_RE = re.compile(r"^\s*[\d,，、\-–－~]+\s*[\(（]?\s*\[?\s*周\s*\]?\s*[\)）]?\s*$")
_PERIOD_ONLY_RE = re.compile(r"^\s*\[\s*[\d\-－,，]+\s*节?\]\s*节?\s*$")


class ParseError(Exception):
    pass


@dataclass
class BigSection:
    index: int
    periods: tuple[int, int]
    start_minutes: int
    end_minutes: int


@dataclass
class ParsedCourse:
    name: str
    weekday: int
    weeks: tuple[int, ...]
    periods: tuple[int, ...]
    start_minutes: int
    end_minutes: int
    teacher: str = ""
    location: str = ""
    descriptor: str = ""
    raw: str = ""

    @property
    def weekday_label(self) -> str:
        return f"周{_WEEKDAYS_LABEL[self.weekday]}"

    @property
    def weeks_label(self) -> str:
        return format_weeks(self.weeks)

    @property
    def time_label(self) -> str:
        return f"{hmm(self.start_minutes)}-{hmm(self.end_minutes)}"


DEFAULT_SECTION_PERIODS = ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16))
DEFAULT_SECTION_TIMES = (
    (8 * 60 + 30, 10 * 60 + 5),
    (10 * 60 + 25, 12 * 60),
    (13 * 60 + 30, 15 * 60 + 5),
    (15 * 60 + 25, 17 * 60),
    (18 * 60, 19 * 60 + 40),
    (19 * 60 + 50, 21 * 60 + 30),
    (21 * 60 + 40, 22 * 60 + 45),
    (22 * 60 + 50, 23 * 60 + 55),
)
DEFAULT_PERIOD_TIMES = {
    period: DEFAULT_SECTION_TIMES[index]
    for index, periods in enumerate(DEFAULT_SECTION_PERIODS)
    for period in periods
}


@dataclass
class ParseResult:
    title: str = ""
    term: str = ""
    big_sections: list[BigSection] = field(default_factory=list)
    courses: list[ParsedCourse] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    has_timetable_times: bool = True

    @property
    def session_count(self) -> int:
        return sum(len(course.weeks) for course in self.courses)


def hmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_weeks(weeks: tuple[int, ...]) -> str:
    """[1,2,3,5,6] -> '1-3,5-6'。"""
    if not weeks:
        return ""
    values = sorted(set(int(value) for value in weeks))
    ranges: list[str] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = value
    ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(ranges)


def _to_minutes(hour: int, minute: int) -> int:
    return hour * 60 + minute


def _parse_big_sections(rows: list[list[str]]) -> tuple[list[BigSection], int, bool]:
    """返回大节列表、表头行号、课表里是否写了大节时间。"""
    header_row = -1
    for index, row in enumerate(rows):
        labels = [cell.strip() for cell in row if cell.strip()]
        if sum(1 for cell in labels if cell in WEEKDAY_NAMES) >= 5:
            header_row = index
            break
    if header_row < 0:
        raise ParseError("没有找到「星期一…星期日」表头，可能不是课表文件。")
    sections: list[BigSection] = []
    has_times = False
    for row in rows[header_row + 1 :]:
        first = (row[0] if row else "").strip()
        if not first:
            continue
        periods_match = _PERIODS_RE.search(first) or _PERIODS_ALT_RE.search(first)
        if not periods_match:
            continue
        periods = (int(periods_match.group(1)), int(periods_match.group(2)))
        match_time = _TIME_RE.search(first)
        if match_time:
            has_times = True
            start = _to_minutes(int(match_time.group(1)), int(match_time.group(2)))
            end = _to_minutes(int(match_time.group(3)), int(match_time.group(4)))
        else:
            mapped = [
                DEFAULT_PERIOD_TIMES[period]
                for period in periods
                if period in DEFAULT_PERIOD_TIMES
            ]
            if not mapped:
                continue
            start = min(item[0] for item in mapped)
            end = max(item[1] for item in mapped)
        sections.append(
            BigSection(
                index=len(sections),
                periods=periods,
                start_minutes=start,
                end_minutes=end,
            )
        )
    if not sections:
        raise ParseError("没有找到「第一大节 (01,02)」或「第1~2节」这样的作息行。")
    return sections, header_row, has_times


def parse_weeks(text: str) -> tuple[int, ...]:
    text = (text or "").strip()
    if not text:
        return ()
    weeks: set[int] = set()
    for token in re.split(r"[,，;；、]", text):
        token = token.strip()
        if not token:
            continue
        odd = "单" in token
        even = "双" in token
        match = re.search(r"(\d+)\s*[-–－~]\s*(\d+)", token)
        if match:
            first, last = int(match.group(1)), int(match.group(2))
        else:
            match = re.search(r"\d+", token)
            if not match:
                continue
            first = last = int(match.group(0))
        if last < first:
            first, last = last, first
        for week in range(first, last + 1):
            if odd and week % 2 == 0:
                continue
            if even and week % 2 == 1:
                continue
            weeks.add(week)
    return tuple(sorted(weeks))


def parse_periods(text: str) -> tuple[int, ...]:
    return tuple(
        int(part) for part in re.split(r"[-－–,，、]", text or "") if part.strip().isdigit()
    )


def _merge_split_schedule(cell: str) -> str:
    """把「1-16[周]」和下一行的「[01-02]节」合成一行。

    曲阜师范大学等教务系统会把周次和节次拆成两行；其余格式不变。
    """
    lines = cell.splitlines()
    for index, line in enumerate(lines):
        if not _PERIOD_ONLY_RE.match(line):
            continue
        for previous in range(index - 1, -1, -1):
            candidate = lines[previous]
            if not candidate.strip():
                break
            if _WEEK_ONLY_RE.match(candidate):
                lines[previous] = candidate.rstrip() + line.strip()
                lines[index] = ""
                break
    return "\n".join(lines)


def _parse_entry(block: str, weekday: int, time_map: dict[int, tuple[int, int]]) -> ParsedCourse | None:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    schedule_index = -1
    for index, line in enumerate(lines):
        if _SCHEDULE_RE.match(line):
            schedule_index = index
            break
    if schedule_index <= 0:
        return None
    match = _SCHEDULE_RE.match(lines[schedule_index])
    assert match is not None
    weeks = parse_weeks(match.group("weeks"))
    periods = parse_periods(match.group("periods"))
    if not weeks or not periods:
        return None
    times = [time_map[period] for period in periods if period in time_map]
    if not times:
        return None
    start = min(item[0] for item in times)
    end = max(item[1] for item in times)
    middle = lines[1:schedule_index]
    descriptor = ""
    teacher = ""
    for line in middle:
        if line.startswith("(") or line.startswith("（"):
            descriptor = line.strip("()（）")
        else:
            teacher = teacher or line
    location = " ".join(lines[schedule_index + 1 :]).strip()
    return ParsedCourse(
        name=lines[0],
        weekday=weekday,
        weeks=weeks,
        periods=periods,
        start_minutes=start,
        end_minutes=end,
        teacher=teacher,
        location=location,
        descriptor=descriptor,
        raw=block.strip(),
    )


def parse_timetable(rows: list[list[str]]) -> ParseResult:
    result = ParseResult()
    if not rows:
        raise ParseError("文件是空的。")
    result.title = (rows[0][0] if rows and rows[0] else "").strip()
    if len(rows) > 1:
        result.term = " ".join(cell for cell in rows[1] if cell.strip()).strip()

    sections, header_row, has_times = _parse_big_sections(rows)
    result.big_sections = sections
    result.has_timetable_times = has_times

    weekday_columns: dict[int, int] = {}
    header = rows[header_row]
    for column, cell in enumerate(header):
        name = (cell or "").strip()
        if name in WEEKDAY_NAMES:
            weekday_columns[WEEKDAY_NAMES[name]] = column
    if len(weekday_columns) < 5:
        raise ParseError("表头缺少星期列。")

    time_map: dict[int, tuple[int, int]] = {}
    for section in sections:
        for period in section.periods:
            if period:
                time_map[period] = (section.start_minutes, section.end_minutes)

    seen: dict[tuple, ParsedCourse] = {}
    for row in rows[header_row + 1 :]:
        first = (row[0] if row else "").strip()
        if not first or not (_TIME_RE.search(first) or _PERIODS_RE.search(first)):
            continue
        for weekday, column in weekday_columns.items():
            if column >= len(row):
                continue
            cell = row[column] or ""
            if not cell.strip():
                continue
            cell = _merge_split_schedule(cell)
            # 空行分隔课程；老师为空时课程名与作息行之间也会多一个空行
            pending: list[str] = []
            for block in re.split(r"\n\s*\n", cell.strip()):
                lines = [line.strip() for line in block.splitlines() if line.strip()]
                if not lines:
                    continue
                schedule_index = next(
                    (index for index, line in enumerate(lines) if _SCHEDULE_RE.match(line)),
                    -1,
                )
                if schedule_index < 0:
                    pending.extend(lines)
                    continue
                header = pending + lines[:schedule_index]
                pending = []
                combined = "\n".join(header + lines[schedule_index:])
                try:
                    course = _parse_entry(combined, weekday, time_map)
                except Exception as exc:  # noqa: BLE001 - 单条解析失败不影响其它行
                    result.warnings.append(f"有一门课解析失败：{exc}")
                    continue
                if course is None:
                    result.warnings.append(f"跳过无法识别的内容：{combined.strip()[:40]}")
                    continue
                key = (
                    course.name,
                    course.teacher,
                    course.location,
                    course.weekday,
                    course.weeks,
                    course.periods,
                )
                if key in seen:
                    continue
                seen[key] = course
    result.courses = sorted(
        seen.values(), key=lambda item: (item.weekday, item.start_minutes, item.name)
    )
    return result




# ---------------------------------------------------------------------------
# 扁平表格（CSV 里常见：每行一门课）
# ---------------------------------------------------------------------------
DEFAULT_PERIOD_TIMES: dict[int, tuple[int, int]] = {
    1: (8 * 60 + 30, 10 * 60 + 5),
    2: (8 * 60 + 30, 10 * 60 + 5),
    3: (10 * 60 + 25, 12 * 60),
    4: (10 * 60 + 25, 12 * 60),
    5: (13 * 60 + 30, 15 * 60 + 5),
    6: (13 * 60 + 30, 15 * 60 + 5),
    7: (15 * 60 + 25, 17 * 60),
    8: (15 * 60 + 25, 17 * 60),
    9: (18 * 60, 19 * 60 + 40),
    10: (18 * 60, 19 * 60 + 40),
    11: (19 * 60 + 50, 21 * 60 + 30),
    12: (19 * 60 + 50, 21 * 60 + 30),
    13: (21 * 60 + 40, 22 * 60 + 45),
    14: (21 * 60 + 40, 22 * 60 + 45),
    15: (22 * 60 + 50, 23 * 60 + 55),
    16: (22 * 60 + 50, 23 * 60 + 55),
}

_HEADER_ALIASES = {
    "name": ("课程", "课程名称", "科目", "名称", "课程名"),
    "weekday": ("星期", "周几", "星期几", "上课星期", "星期天"),
    "periods": ("节次", "小节", "节", "上课节次"),
    "weeks": ("周次", "周数", "上课周次"),
    "time": ("时间", "上课时间", "时段"),
    "location": ("地点", "教室", "上课地点", "场地"),
    "teacher": ("教师", "老师", "任课教师"),
}


def _find_column(headers: list[str], key: str) -> int | None:
    for index, header in enumerate(headers):
        clean = re.sub(r"[\s*＊:：()（）]", "", header)
        for alias in _HEADER_ALIASES[key]:
            if alias in clean:
                return index
    return None


def parse_flat_rows(rows: list[list[str]]) -> ParseResult:
    """解析「一行一门课」的 CSV：课程/星期/节次/周次[/时间/地点/教师]。"""
    if not rows:
        raise ParseError("文件是空的。")
    header_index = -1
    for index, row in enumerate(rows[:10]):
        cells = [cell.strip() for cell in row]
        if any(cells) and _find_column(cells, "name") is not None and _find_column(cells, "weekday") is not None:
            header_index = index
            break
    if header_index < 0:
        raise ParseError("没有找到「课程、星期」这样的表头，无法按 CSV 识别。")
    headers = [cell.strip() for cell in rows[header_index]]
    columns = {key: _find_column(headers, key) for key in _HEADER_ALIASES}
    result = ParseResult(title="CSV 课表")
    has_times = False
    seen: dict[tuple, ParsedCourse] = {}
    for row in rows[header_index + 1 :]:
        if not any(cell.strip() for cell in row):
            continue

        def value(key: str) -> str:
            index = columns.get(key)
            if index is None or index >= len(row):
                return ""
            return (row[index] or "").strip()

        name = re.sub(r"[●◆★☆■□]+$", "", value("name")).strip()
        if not name:
            continue
        weekday = _parse_weekday(value("weekday"))
        if weekday is None:
            result.warnings.append(f"跳过（星期无法识别）：{name}")
            continue
        weeks = parse_weeks(value("weeks"))
        if not weeks:
            result.warnings.append(f"跳过（周次无法识别）：{name}")
            continue
        periods = tuple(int(part) for part in re.findall(r"\d+", value("periods")))
        if not periods:
            result.warnings.append(f"跳过（节次无法识别）：{name}")
            continue
        times = _parse_time_range(value("time"))
        if times is not None:
            has_times = True
        if times is None:
            mapped = [DEFAULT_PERIOD_TIMES[p] for p in periods if p in DEFAULT_PERIOD_TIMES]
            if not mapped:
                result.warnings.append(f"跳过（缺少时间）：{name}")
                continue
            times = (min(item[0] for item in mapped), max(item[1] for item in mapped))
        course = ParsedCourse(
            name=name,
            weekday=weekday,
            weeks=weeks,
            periods=periods,
            start_minutes=times[0],
            end_minutes=times[1],
            teacher=value("teacher"),
            location=value("location"),
            raw=" | ".join(cell.strip() for cell in row if cell.strip()),
        )
        key = (course.name, course.teacher, course.location, course.weekday, course.weeks, course.periods)
        seen.setdefault(key, course)
    if not seen:
        raise ParseError("表格里没有解析出任何课程。")
    result.courses = sorted(seen.values(), key=lambda item: (item.weekday, item.start_minutes, item.name))
    result.has_timetable_times = has_times
    return result


def _parse_weekday(text: str) -> int | None:
    clean = (text or "").strip()
    for name, index in WEEKDAY_NAMES.items():
        if name in clean:
            return index
    match = re.search(r"([1-7])", clean)
    if match:
        return int(match.group(1)) - 1
    for index, label in enumerate("一二三四五六日"):
        if clean == label:
            return index
    return None


def _parse_time_range(text: str) -> tuple[int, int] | None:
    match = _TIME_RE.search(text or "")
    if not match:
        return None
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    if end <= start:
        return None
    return start, end


def apply_times(
    courses: list[ParsedCourse],
    period_times: dict[int, tuple[int, int]],
) -> list[ParsedCourse]:
    """用用户设置或课表里的节次时间，重算每门课的起止时间。"""
    updated: list[ParsedCourse] = []
    for course in courses:
        mapped = [period_times[p] for p in course.periods if p in period_times]
        if not mapped:
            updated.append(course)
            continue
        updated.append(
            replace(
                course,
                start_minutes=min(item[0] for item in mapped),
                end_minutes=max(item[1] for item in mapped),
            )
        )
    return updated


def expand_sessions(
    courses: list[ParsedCourse], semester_start: date
) -> list[tuple[ParsedCourse, date, int, int]]:
    """按学期第一周周一展开成具体日期。"""
    sessions: list[tuple[ParsedCourse, date, int, int]] = []
    monday = semester_start - timedelta(days=semester_start.weekday())
    for course in courses:
        for week in course.weeks:
            day = monday + timedelta(days=(week - 1) * 7 + course.weekday)
            sessions.append((course, day, course.start_minutes, course.end_minutes))
    return sessions
