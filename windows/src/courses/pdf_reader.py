"""从 PDF 课表里提取表格（基于 pypdfium2 的字符坐标，尽力而为）。

只处理「文字版」PDF：能定位到星期表头和大节行时，按列/行还原成和 .xls 一样的
二维文本，再交给 :func:`parse_timetable`。扫描版/图片版会给出明确提示。
"""

from __future__ import annotations

import re
from pathlib import Path

from .timetable_parser import WEEKDAY_NAMES, ParseError, parse_timetable

WEEKDAY_ORDER = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _load_pdfium():
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - 打包时已包含
        raise ParseError(
            "当前版本缺少 PDF 解析组件。可以改用「从文本粘贴」，或者导出 .xls / .csv。"
        ) from exc
    return pdfium


def _page_lines(page) -> list[dict]:
    textpage = page.get_textpage()
    count = textpage.count_chars()
    items: list[tuple[str, float, float, float, float]] = []
    for index in range(count):
        text = textpage.get_text_range(index, 1)
        if not text.strip():
            continue
        left, bottom, right, top = textpage.get_charbox(index)
        items.append((text, left, bottom, right, top))
    lines: list[dict] = []
    for text, left, bottom, right, top in items:
        for line in lines:
            if abs(line["top"] - top) <= 3:
                line["chars"].append((left, text))
                break
        else:
            lines.append({"top": top, "chars": [(left, text)]})
    for line in lines:
        line["chars"].sort(key=lambda item: item[0])
        line["text"] = "".join(text for _, text in line["chars"])
    lines.sort(key=lambda line: -line["top"])
    return lines


def _weekday_columns(header: dict) -> list[float] | None:
    text = header["text"]
    positions: list[float] = []
    for name in WEEKDAY_ORDER:
        index = text.find(name)
        if index < 0:
            return None
        # 表头文字里第 index 个字符对应的 x（跳过空白）
        visible = [item for item in header["chars"] if item[1].strip()]
        if index >= len(visible):
            return None
        positions.append(visible[index][0])
    return positions


def _cell_text(lines: list[dict]) -> str:
    if not lines:
        return ""
    lines = sorted(lines, key=lambda line: -line["top"])
    parts: list[str] = []
    previous_top = None
    for line in lines:
        text = line["text"].strip()
        if not text:
            continue
        if previous_top is not None and previous_top - line["top"] > 22:
            parts.append("")
        parts.append(text)
        previous_top = line["top"]
    return "\n".join(parts)


def _build_rows_from_page(page) -> list[list[str]] | None:
    lines = _page_lines(page)
    header = next(
        (
            line
            for line in lines
            if sum(1 for name in WEEKDAY_ORDER if name in line["text"]) >= 5
        ),
        None,
    )
    if header is None:
        return None
    columns = _weekday_columns(header)
    if columns is None:
        return None
    boundaries = [columns[0] - (columns[1] - columns[0]) / 2]
    for index in range(1, len(columns)):
        boundaries.append((columns[index - 1] + columns[index]) / 2)
    boundaries.append(columns[-1] + (columns[-1] - columns[-2]) / 2)

    anchors = [line for line in lines if "大节" in line["text"]]
    if not anchors:
        return None
    anchors.sort(key=lambda line: -line["top"])
    groups: list[list[dict]] = [[] for _ in anchors]
    for line in lines:
        if line is header or "大节" in line["text"]:
            continue
        for index, anchor in enumerate(anchors):
            if line["top"] <= anchor["top"] + 2:
                groups[index].append(line)
                break

    rows: list[list[str]] = [[""] + list(WEEKDAY_ORDER)]
    for index, anchor in enumerate(anchors):
        label_parts = [anchor]
        for line in groups[index]:
            center = sum(item[0] for item in line["chars"]) / max(1, len(line["chars"]))
            if center < boundaries[1]:
                label_parts.append(line)
        row = [""] * 8
        row[0] = _cell_text(label_parts)
        for column in range(1, 8):
            collected = []
            for line in groups[index]:
                center = sum(item[0] for item in line["chars"]) / max(1, len(line["chars"]))
                column_index = 0
                for position in range(1, 8):
                    if center >= boundaries[position]:
                        column_index = position
                    else:
                        break
                if column_index == column:
                    collected.append(line)
            row[column] = _cell_text(collected)
        rows.append(row)
    return rows


def read_pdf_rows(path: str | Path) -> list[list[str]]:
    pdfium = _load_pdfium()
    try:
        document = pdfium.PdfDocument(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"无法打开 PDF：{exc}") from exc
    combined: list[list[str]] | None = None
    try:
        for index in range(len(document)):
            page = document[index]
            rows = _build_rows_from_page(page)
            if rows is None:
                continue
            if combined is None:
                combined = rows
            else:
                combined.extend(rows[1:])
    finally:
        try:
            document.close()
        except Exception:  # noqa: BLE001
            pass
    if not combined:
        raise ParseError(
            "这个 PDF 里没有找到课表文字（可能是扫描版/图片）。"
            "请用 PDF 阅读器全选复制，再点「从文本粘贴」导入；或改用 .xls / .csv。"
        )
    # 至少能解析出课程才算成功
    parse_timetable(combined)
    return combined
