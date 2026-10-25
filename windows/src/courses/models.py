"""课表数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CourseBlock:
    """周视图里的一节课（已展开到具体日期）。"""

    course_id: int
    name: str
    location: str
    color: str
    day: date
    start_minutes: int
    end_minutes: int
    teacher: str = ""

    @property
    def time_label(self) -> str:
        return f"{self.start_minutes // 60:02d}:{self.start_minutes % 60:02d}-" \
               f"{self.end_minutes // 60:02d}:{self.end_minutes % 60:02d}"

    @property
    def tooltip(self) -> str:
        parts = [self.name]
        if self.teacher:
            parts.append(self.teacher)
        if self.location:
            parts.append(self.location)
        return " · ".join(parts) + f"\n{self.time_label}"
