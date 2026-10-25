"""课表持久化：课程 + 每次课的日期时间，保存在日程库（planner.db）。

课程表是独立的一层，不会变成任务，也不会进入提醒队列；
删除课程只影响课程表本身。
"""

from __future__ import annotations

from datetime import date, datetime

from ..database import Database, DatabaseError
from .models import CourseBlock
from .timetable_parser import ParseResult, ParsedCourse, expand_sessions

COURSE_COLORS = (
    "#6C8AE4",
    "#D79A38",
    "#57AE84",
    "#C97F6B",
    "#9B87E8",
    "#5FA8A0",
    "#DD7BA6",
    "#8C8FE0",
)


class CourseStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def replace(self, parsed: ParseResult, semester_start: date) -> tuple[int, int]:
        """用解析结果整体替换课程表，返回（课程数, 上课次数）。"""
        groups: dict[tuple[str, str, str, str], list[ParsedCourse]] = {}
        for course in parsed.courses:
            key = (course.name, course.teacher, course.location, course.descriptor)
            groups.setdefault(key, []).append(course)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            with self.db.transaction() as connection:
                connection.execute("DELETE FROM course_sessions")
                connection.execute("DELETE FROM courses")
                for index, (key, items) in enumerate(groups.items()):
                    name, teacher, location, descriptor = key
                    color = COURSE_COLORS[index % len(COURSE_COLORS)]
                    cursor = connection.execute(
                        "INSERT INTO courses(name, teacher, location, descriptor, color, "
                        "created_at) VALUES(?, ?, ?, ?, ?, ?)",
                        (name, teacher, location, descriptor, color, now),
                    )
                    course_id = int(cursor.lastrowid)
                    for course, day, start, end in expand_sessions(items, semester_start):
                        connection.execute(
                            "INSERT INTO course_sessions(course_id, day, start_minutes, "
                            "end_minutes, skipped) VALUES(?, ?, ?, ?, 0)",
                            (course_id, day.isoformat(), start, end),
                        )
            return self.stats()
        except DatabaseError:
            raise

    def clear(self) -> None:
        with self.db.transaction() as connection:
            connection.execute("DELETE FROM course_sessions")
            connection.execute("DELETE FROM courses")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def blocks_between(self, start: date, end: date) -> list[CourseBlock]:
        rows = self.db.query(
            """
            SELECT s.course_id, s.day, s.start_minutes, s.end_minutes,
                   c.name, c.location, c.color, c.teacher
            FROM course_sessions s
            JOIN courses c ON c.id = s.course_id
            WHERE s.skipped = 0 AND s.day >= ? AND s.day <= ?
            ORDER BY s.day, s.start_minutes
            """,
            (start.isoformat(), end.isoformat()),
        )
        blocks: list[CourseBlock] = []
        for row in rows:
            try:
                day = date.fromisoformat(row["day"])
            except ValueError:
                continue
            blocks.append(
                CourseBlock(
                    course_id=int(row["course_id"]),
                    name=row["name"],
                    location=row["location"] or "",
                    color=row["color"] or COURSE_COLORS[0],
                    day=day,
                    start_minutes=int(row["start_minutes"]),
                    end_minutes=int(row["end_minutes"]),
                    teacher=row["teacher"] or "",
                )
            )
        return blocks

    def stats(self) -> tuple[int, int]:
        courses = int(self.db.scalar("SELECT COUNT(*) FROM courses") or 0)
        sessions = int(self.db.scalar("SELECT COUNT(*) FROM course_sessions") or 0)
        return courses, sessions

    def course_names(self) -> list[str]:
        return [row["name"] for row in self.db.query("SELECT name FROM courses ORDER BY name")]
