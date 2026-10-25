"""课表导入向导：选择导出文件 → 填第 1 周周一 → 预览 → 导入。"""

from __future__ import annotations

import csv
import io
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..database import DatabaseError
from ..time_utils import WEEKDAY_LABELS
from .course_store import CourseStore
from .timetable_parser import (
    DEFAULT_SECTION_PERIODS,
    DEFAULT_SECTION_TIMES,
    apply_times,
    ParsedCourse,
    WEEKDAY_NAMES,
    ParseError,
    ParseResult,
    parse_flat_rows,
    parse_timetable,
)

SUFFIXES = (".xls", ".xlsx", ".csv", ".pdf")


def read_table_rows(path: str | Path) -> list[list[str]]:
    suffix = str(path).lower()
    if suffix.endswith(".xls"):
        from .xls_reader import read_xls_rows

        return read_xls_rows(path)
    if suffix.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - 打包时已包含
            raise ParseError("当前版本不支持 .xlsx，请用 .xls 或 .csv 文件。") from exc
        workbook = load_workbook(path, data_only=True)
        first_rows: list[list[str]] | None = None
        for sheet in workbook.worksheets:
            rows: list[list[str]] = []
            for row in sheet.iter_rows(values_only=True):
                rows.append(["" if value is None else str(value) for value in row])
            if not any(any(cell.strip() for cell in row) for row in rows):
                continue
            if first_rows is None:
                first_rows = rows
            if _looks_like_flat_sheet(rows):
                return rows
        if first_rows is None:
            raise ParseError("Excel 文件是空的。")
        return first_rows
    if suffix.endswith(".csv") or suffix.endswith(".txt"):
        return read_csv_rows(Path(path).read_bytes())
    if suffix.endswith(".pdf"):
        from .pdf_reader import read_pdf_rows

        return read_pdf_rows(path)
    raise ParseError("只支持 .xls / .xlsx / .csv / .pdf 文件。")


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_csv_rows(data: bytes | str) -> list[list[str]]:
    text = data if isinstance(data, str) else _decode_text(data)
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        reader = csv.reader(io.StringIO(text), dialect)
    except csv.Error:
        reader = csv.reader(io.StringIO(text), delimiter=",")
    rows = [list(row) for row in reader]
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()
    return rows


def _looks_like_flat_sheet(rows: list[list[str]]) -> bool:
    """表头里同时有课程名和星期/节次，说明是「一行一门课」的明细表。"""
    for row in rows[:10]:
        cells = [cell.strip() for cell in row]
        has_name = any("课程名称" in cell or cell == "课程" for cell in cells)
        has_day = any("星期" in cell for cell in cells)
        if has_name and has_day:
            return True
    return False


def looks_like_grid(rows: list[list[str]]) -> bool:
    for row in rows[:10]:
        if sum(1 for cell in row if cell.strip() in WEEKDAY_NAMES) >= 5:
            return True
    return False


def parse_rows(rows: list[list[str]]) -> ParseResult:
    return parse_timetable(rows) if looks_like_grid(rows) else parse_flat_rows(rows)


class PasteTextDialog(QDialog):
    """把从 PDF / 网页 / Excel 里复制的表格文本粘贴进来。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("粘贴课表文本")
        self.setMinimumSize(620, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel("粘贴课表文本")
        title.setObjectName("Title")
        layout.addWidget(title)
        hint = QLabel(
            "在 PDF 阅读器、网页或 Excel 里全选课表内容并复制，粘贴到下面。"
            "如果是 PDF：打开 PDF → Ctrl+A → Ctrl+C → 粘到这里。"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        from PySide6.QtWidgets import QPlainTextEdit

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("在这里粘贴表格文本…")
        layout.addWidget(self.editor, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("解析")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(ok)
        layout.addLayout(footer)

    def text(self) -> str:
        return self.editor.toPlainText()


class TimetableImportDialog(QDialog):
    def __init__(self, store: CourseStore, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.parsed: ParseResult | None = None
        self.setWindowTitle("导入课表")
        self.setModal(True)
        self.setMinimumWidth(720)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 18)
        outer.setSpacing(12)

        title = QLabel("导入课表")
        title.setObjectName("Title")
        outer.addWidget(title)
        hint = QLabel(
            "支持教务系统导出的 .xls / .xlsx，也支持 .csv 和文字版 .pdf。"
            "PDF 版式千差万别，如果提取失败，请打开 PDF 全选复制，点「从文本粘贴」。"
            "填好这学期第 1 周的星期一，课程会按周次展开到周视图里。"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("选择 .xls 文件")
        file_row.addWidget(self.path_edit, 1)
        browse = QPushButton("选择文件…")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self._browse)
        file_row.addWidget(browse)
        paste = QPushButton("从文本粘贴…")
        paste.setCursor(Qt.CursorShape.PointingHandCursor)
        paste.clicked.connect(self._paste)
        file_row.addWidget(paste)
        outer.addLayout(file_row)

        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        date_row.addWidget(QLabel("第 1 周的星期一"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(self._default_start())
        self.date_edit.setFixedWidth(130)
        date_row.addWidget(self.date_edit)
        self.reparse_button = QPushButton("重新解析")
        self.reparse_button.setObjectName("Ghost")
        self.reparse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reparse_button.clicked.connect(lambda: self._parse(self.path_edit.text()))
        date_row.addWidget(self.reparse_button)
        date_row.addStretch(1)
        self.existing_label = QLabel("")
        self.existing_label.setObjectName("Muted")
        date_row.addWidget(self.existing_label)
        outer.addLayout(date_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["课程", "星期", "时间", "周次", "地点", "教师"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(260)
        self.table.horizontalHeader().setStretchLastSection(True)
        outer.addWidget(self.table)

        time_row = QHBoxLayout()
        time_row.setSpacing(12)
        time_row.addWidget(QLabel("课程时间"))
        self.use_parsed_radio = QRadioButton("使用课表时间")
        self.use_custom_radio = QRadioButton("自定义每节时间")
        self.use_parsed_radio.setChecked(True)
        time_row.addWidget(self.use_parsed_radio)
        time_row.addWidget(self.use_custom_radio)
        time_row.addStretch(1)
        outer.addLayout(time_row)

        self.time_hint = QLabel("")
        self.time_hint.setObjectName("Muted")
        self.time_hint.setWordWrap(True)
        outer.addWidget(self.time_hint)

        self.custom_times_box = QWidget()
        grid = QGridLayout(self.custom_times_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        self.custom_edits: list[tuple[QTimeEdit, QTimeEdit]] = []
        for index, (periods, times) in enumerate(
            zip(DEFAULT_SECTION_PERIODS, DEFAULT_SECTION_TIMES)
        ):
            grid.addWidget(QLabel(f"第 {periods[0]}-{periods[1]} 节"), index, 0)
            start_edit = QTimeEdit(QTime(times[0] // 60, times[0] % 60))
            end_edit = QTimeEdit(QTime(times[1] // 60, times[1] % 60))
            for edit in (start_edit, end_edit):
                edit.setDisplayFormat("HH:mm")
                edit.setFixedWidth(80)
                edit.timeChanged.connect(self._refresh_time_preview)
            grid.addWidget(start_edit, index, 1)
            grid.addWidget(QLabel("—"), index, 2)
            grid.addWidget(end_edit, index, 3)
            self.custom_edits.append((start_edit, end_edit))
        self.custom_scroll = QScrollArea()
        self.custom_scroll.setWidgetResizable(True)
        self.custom_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.custom_scroll.setWidget(self.custom_times_box)
        self.custom_scroll.setMaximumHeight(190)
        self.custom_scroll.setVisible(False)
        outer.addWidget(self.custom_scroll)

        self.use_parsed_radio.toggled.connect(self._on_time_mode_changed)
        self.use_custom_radio.toggled.connect(self._on_time_mode_changed)

        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        outer.addWidget(self.summary)

        self.clear_check = QCheckBox("导入前清空已有课程（推荐）")
        self.clear_check.setChecked(True)
        outer.addWidget(self.clear_check)

        self.error_label = QLabel("")
        self.error_label.setObjectName("ErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        outer.addWidget(self.error_label)

        line = QFrame()
        line.setObjectName("Separator")
        line.setFixedHeight(1)
        outer.addWidget(line)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.import_button = QPushButton("导入")
        self.import_button.setObjectName("Primary")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import)
        self.clear_button = QPushButton("清空课程表")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self._clear)
        cancel = QPushButton("关闭")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        footer.addWidget(self.clear_button)
        footer.addStretch(1)
        footer.addWidget(cancel)
        footer.addWidget(self.import_button)
        outer.addLayout(footer)

        self._refresh_existing()

    # ------------------------------------------------------------------
    def _default_start(self) -> QDate:
        stored = self.settings.get_str("course_semester_start")
        if stored:
            try:
                value = date.fromisoformat(stored)
                return QDate(value.year, value.month, value.day)
            except ValueError:
                pass
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        return QDate(monday.year, monday.month, monday.day)

    def _refresh_existing(self) -> None:
        courses, sessions = self.store.stats()
        self.existing_label.setText(
            f"当前已有 {courses} 门课、{sessions} 次课" if courses else "当前还没有课程"
        )

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择课表文件", "", "课表文件 (*.xls *.xlsx *.csv *.pdf);;所有文件 (*.*)"
        )
        if path:
            self.path_edit.setText(path)
            self._parse(path)

    def _parse(self, path: str) -> None:
        if not path:
            return
        try:
            rows = read_table_rows(path)
        except (ParseError, OSError, ValueError) as exc:
            self._show_error(f"读取文件失败：{exc}")
            return
        self._apply_rows(rows, path)

    def _paste(self) -> None:
        dialog = PasteTextDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        content = dialog.text()
        if not content.strip():
            self._show_error("粘贴的内容是空的。")
            return
        rows = read_csv_rows(content)
        self._apply_rows(rows, "（粘贴的文本）")

    def _apply_rows(self, rows: list[list[str]], source: str) -> None:
        self.path_edit.setText(source)
        self.error_label.setVisible(False)
        self.table.setRowCount(0)
        self.parsed = None
        self.import_button.setEnabled(False)
        try:
            parsed = parse_rows(rows)
        except (ParseError, ValueError) as exc:
            self._show_error(f"解析失败：{exc}")
            return
        self.parsed = parsed
        self.use_parsed_radio.setEnabled(parsed.has_timetable_times)
        if parsed.has_timetable_times:
            self.use_parsed_radio.setChecked(True)
        else:
            self.use_custom_radio.setChecked(True)
        self._on_time_mode_changed()
        self._fill_table(parsed, courses=self._display_courses())
        groups = {
            (item.name, item.teacher, item.location, item.descriptor) for item in parsed.courses
        }
        sessions = sum(len(item.weeks) for item in parsed.courses)
        self.summary.setText(
            f"共 {len(groups)} 门课程 · {sessions} 次课"
            + (f" · {len(parsed.warnings)} 条提示" if parsed.warnings else "")
        )
        self.import_button.setEnabled(bool(parsed.courses))

    def _fill_table(
        self, parsed: ParseResult, courses: list[ParsedCourse] | None = None
    ) -> None:
        courses = courses if courses is not None else parsed.courses
        self.table.setRowCount(len(courses))
        for row, course in enumerate(courses):
            values = [
                course.name,
                WEEKDAY_LABELS[course.weekday],
                course.time_label,
                course.weeks_label,
                course.location or "—",
                course.teacher or "—",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setToolTip(course.raw or course.name)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if self.table.columnWidth(0) > 240:
            self.table.setColumnWidth(0, 240)

    def _on_time_mode_changed(self) -> None:
        if not hasattr(self, "custom_scroll"):
            return
        custom = self.use_custom_radio.isChecked()
        self.custom_scroll.setVisible(custom)
        if self.parsed is None:
            return
        if not self.parsed.has_timetable_times:
            self.time_hint.setText("课表里没有节次时间，请设置每节课的起止时间后再导入。")
            self.time_hint.setStyleSheet("color: #C0392B;")
        elif custom:
            self.time_hint.setText("自定义时间会按节次套用到所有课程。")
            self.time_hint.setStyleSheet("")
        else:
            self.time_hint.setText("使用课表里写的大节时间。")
            self.time_hint.setStyleSheet("")
        self._refresh_time_preview()

    def _custom_period_times(self) -> dict[int, tuple[int, int]]:
        result: dict[int, tuple[int, int]] = {}
        for index, (start_edit, end_edit) in enumerate(self.custom_edits):
            start_time = start_edit.time()
            end_time = end_edit.time()
            start = start_time.hour() * 60 + start_time.minute()
            end = end_time.hour() * 60 + end_time.minute()
            if end <= start:
                end = start + 45
            for period in DEFAULT_SECTION_PERIODS[index]:
                result[period] = (start, end)
        return result

    def _display_courses(self) -> list[ParsedCourse]:
        if self.parsed is None:
            return []
        if self.use_custom_radio.isChecked():
            return apply_times(self.parsed.courses, self._custom_period_times())
        return self.parsed.courses

    def _refresh_time_preview(self) -> None:
        if self.parsed is None or not hasattr(self, "custom_edits"):
            return
        self._fill_table(self.parsed, courses=self._display_courses())

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.summary.setText("")

    def _start_date(self) -> date:
        value = self.date_edit.date()
        return date(value.year(), value.month(), value.day())

    def _import(self) -> None:
        if self.parsed is None or not self.parsed.courses:
            self._show_error("还没有可导入的课程。")
            return
        if self.clear_check.isChecked():
            try:
                self.store.clear()
            except DatabaseError as exc:
                self._show_error(f"清空旧课程失败：{exc}")
                return
        try:
            result = replace(self.parsed, courses=self._display_courses())
            courses, sessions = self.store.replace(result, self._start_date())
        except DatabaseError as exc:
            self._show_error(f"保存失败：{exc}")
            return
        except Exception as exc:  # noqa: BLE001 - 导入失败给出可读提示
            self._show_error(f"保存失败：{exc}")
            return
        self.settings.set("course_semester_start", self._start_date().isoformat())
        QMessageBox.information(
            self,
            "导入完成",
            f"已导入 {courses} 门课程、{sessions} 次课。\n"
            "关掉这个窗口后，周视图里就能看到课程了。",
        )
        self.accept()

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空课程表",
            "确定删除所有课程和上课记录吗？这不会影响任务和提醒。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.clear()
        except DatabaseError as exc:
            self._show_error(f"清空失败：{exc}")
            return
        self._refresh_existing()
        self.table.setRowCount(0)
        self.summary.setText("课程表已清空。")
        self.import_button.setEnabled(False)


from pathlib import Path  # noqa: E402  (仅用于类型注解)
