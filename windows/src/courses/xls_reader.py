"""读取旧版 Excel（.xls，BIFF8）文件的表格内容。

教务系统导出的课表通常是 BIFF8 格式的 .xls。PySide6 运行时不带 xlrd，
这里实现一个只读的最小解析器（OLE2 复合文档 + BIFF8 记录），只关心
「单元格文本」：SST / LABELSST / NUMBER / RK / MULRK / LABEL / FORMULA。

外部只使用 :func:`read_xls_rows`，返回 ``list[list[str]]``（第一个工作表）。
"""

from __future__ import annotations

import struct
from pathlib import Path

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class XlsError(Exception):
    """不是可读的 xls 文件。"""


# ---------------------------------------------------------------------------
# OLE2 复合文档
# ---------------------------------------------------------------------------
class _CompoundFile:
    def __init__(self, data: bytes) -> None:
        if not data.startswith(OLE_MAGIC):
            raise XlsError("不是有效的 .xls 文件。")
        self.data = data
        self.sector_size = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mini_sector_size = 1 << struct.unpack_from("<H", data, 0x20)[0]
        self.difat_start = struct.unpack_from("<I", data, 0x44)[0]
        self.difat_count = struct.unpack_from("<I", data, 0x48)[0]
        self.fat_count = struct.unpack_from("<I", data, 0x2C)[0]
        self.dir_start = struct.unpack_from("<I", data, 0x30)[0]
        self.mini_cutoff = struct.unpack_from("<I", data, 0x38)[0]
        self.minifat_start = struct.unpack_from("<I", data, 0x3C)[0]
        self.minifat_count = struct.unpack_from("<I", data, 0x40)[0]
        self._fat = self._load_fat()
        self._minifat = self._load_chain(self.minifat_start, self.minifat_count)
        self.entries = self._load_directory()
        root = next((e for e in self.entries if e["type"] == 5), None)
        if root is None:
            raise XlsError("xls 文件缺少根目录。")
        self._mini_stream = self._read_chain(root["start"], root["size"])
        self._root_start = root["start"]

    # -- 扇区读取 ------------------------------------------------------
    def _sector(self, index: int) -> bytes:
        offset = 512 + index * self.sector_size
        return self.data[offset : offset + self.sector_size]

    def _load_chain(self, start: int, count: int) -> list[int]:
        if start in (0xFFFFFFFF, 0xFFFFFFFE) or count == 0:
            return []
        values: list[int] = []
        for index in range(count):
            raw = self._sector(start + index)
            values.extend(struct.unpack("<%dI" % (len(raw) // 4), raw))
        return values

    def _load_fat(self) -> list[int]:
        difat = list(struct.unpack_from("<109I", self.data, 0x4C))
        sector = self.difat_start
        remaining = self.difat_count
        while remaining > 0 and sector not in (0xFFFFFFFE, 0xFFFFFFFF):
            raw = self._sector(sector)
            entries = struct.unpack("<%dI" % (len(raw) // 4), raw)
            difat.extend(entries[:-1])
            sector = entries[-1]
            remaining -= 1
        fat: list[int] = []
        for index in difat:
            if index in (0xFFFFFFFE, 0xFFFFFFFF) or len(fat) >= self.fat_count * (self.sector_size // 4):
                continue
            raw = self._sector(index)
            fat.extend(struct.unpack("<%dI" % (len(raw) // 4), raw))
        return fat

    def _read_chain(self, start: int, size: int) -> bytes:
        if size == 0:
            return b""
        chunks: list[bytes] = []
        sector = start
        guard = 0
        while sector not in (0xFFFFFFFE, 0xFFFFFFFF) and guard < 100000:
            chunks.append(self._sector(sector))
            guard += 1
            if sector >= len(self._fat):
                break
            nxt = self._fat[sector]
            if nxt == sector:
                break
            sector = nxt
        return b"".join(chunks)[:size]

    def _read_mini_chain(self, start: int, size: int) -> bytes:
        chunks: list[bytes] = []
        sector = start
        guard = 0
        while sector not in (0xFFFFFFFE, 0xFFFFFFFF) and guard < 100000:
            offset = sector * self.mini_sector_size
            chunks.append(self._mini_stream[offset : offset + self.mini_sector_size])
            guard += 1
            if sector >= len(self._minifat):
                break
            sector = self._minifat[sector]
        return b"".join(chunks)[:size]

    def _load_directory(self) -> list[dict]:
        entries: list[dict] = []
        for sector in self._chain(self.dir_start):
            raw = self._sector(sector)
            for offset in range(0, len(raw), 128):
                entry = raw[offset : offset + 128]
                if len(entry) < 128:
                    break
                name_len = struct.unpack_from("<H", entry, 0x40)[0]
                if name_len < 2:
                    continue
                name = entry[: name_len - 2].decode("utf-16-le", errors="replace")
                entry_type = entry[0x42]
                start = struct.unpack_from("<I", entry, 0x74)[0]
                size = struct.unpack_from("<Q", entry, 0x78)[0]
                entries.append({"name": name, "type": entry_type, "start": start, "size": size})
        return entries

    def _chain(self, start: int) -> list[int]:
        result: list[int] = []
        sector = start
        guard = 0
        while sector not in (0xFFFFFFFE, 0xFFFFFFFF) and guard < 100000:
            result.append(sector)
            guard += 1
            if sector >= len(self._fat):
                break
            nxt = self._fat[sector]
            if nxt == sector:
                break
            sector = nxt
        return result

    def stream(self, name: str) -> bytes:
        entry = next((e for e in self.entries if e["type"] == 2 and e["name"] == name), None)
        if entry is None:
            raise XlsError(f"xls 文件里没有 {name} 数据流。")
        if entry["size"] < self.mini_cutoff:
            return self._read_mini_chain(entry["start"], entry["size"])
        return self._read_chain(entry["start"], entry["size"])


# ---------------------------------------------------------------------------
# BIFF8 记录
# ---------------------------------------------------------------------------
def _records(stream: bytes):
    offset = 0
    length = len(stream)
    while offset + 4 <= length:
        record_type, size = struct.unpack_from("<HH", stream, offset)
        offset += 4
        payload = stream[offset : offset + size]
        offset += size
        yield record_type, payload


def _decode_rk(value: int) -> float:
    if value & 0x02:
        number = value >> 2
        if number & 0x20000000:
            number -= 0x40000000
        return float(number)
    raw = struct.pack("<I", value & 0xFFFFFFFC) + b"\x00" * 4
    return struct.unpack("<d", raw[4:] + raw[:4])[0] if False else struct.unpack("<d", raw)[0] / 100.0


def _rk_value(value: int) -> float:
    # RK 编码：bit0=1 表示乘 100 的整数，bit1=1 表示整数
    if value & 0x02:
        number = value >> 2
        if number & 0x20000000:
            number -= 0x40000000
        return float(number) / (100.0 if value & 0x01 else 1.0)
    raw = struct.pack("<I", value & 0xFFFFFFFC)
    number = struct.unpack("<d", raw + b"\x00\x00\x00\x00")[0]
    return number / (100.0 if value & 0x01 else 1.0)


def _read_unicode_string(data: bytes, offset: int, *, length_size: int = 2):
    if length_size == 1:
        count = data[offset]
        offset += 1
    else:
        count = struct.unpack_from("<H", data, offset)[0]
        offset += 2
    flags = data[offset]
    offset += 1
    wide = bool(flags & 0x01)
    has_rich = bool(flags & 0x08)
    has_ext = bool(flags & 0x04)
    runs = 0
    ext_size = 0
    if has_rich:
        runs = struct.unpack_from("<H", data, offset)[0]
        offset += 2
    if has_ext:
        ext_size = struct.unpack_from("<I", data, offset)[0]
        offset += 4
    byte_count = count * 2 if wide else count
    raw = data[offset : offset + byte_count]
    offset += byte_count
    text = raw.decode("utf-16-le", errors="replace") if wide else raw.decode("latin-1")
    offset += runs * 4 + ext_size
    return text, offset


class _BoundaryReader:
    """按记录边界读取 SST 字符数据（跨 CONTINUE 时读编码标志位）。"""

    def __init__(self, payloads: list[bytes]) -> None:
        self.payloads = payloads
        self.index = 0
        self.offset = 0

    def _current(self) -> bytes:
        return self.payloads[self.index]

    def at_end(self) -> bool:
        while self.index < len(self.payloads) and self.offset >= len(self.payloads[self.index]):
            self.index += 1
            self.offset = 0
        return self.index >= len(self.payloads)

    def read_raw(self, count: int) -> bytes:
        chunks: list[bytes] = []
        while count > 0:
            if self.at_end():
                raise XlsError("SST 数据不完整。")
            current = self._current()
            take = min(count, len(current) - self.offset)
            chunks.append(current[self.offset : self.offset + take])
            self.offset += take
            count -= take
        return b"".join(chunks)

    def read_string(self) -> str:
        if self.at_end():
            return ""
        header = self.read_raw(3)
        count = struct.unpack_from("<H", header, 0)[0]
        flags = header[2]
        wide = bool(flags & 0x01)
        has_rich = bool(flags & 0x08)
        has_ext = bool(flags & 0x04)
        runs = 0
        ext_size = 0
        if has_rich:
            runs = struct.unpack_from("<H", self.read_raw(2), 0)[0]
        if has_ext:
            ext_size = struct.unpack_from("<I", self.read_raw(4), 0)[0]
        chars: list[str] = []
        remaining = count
        while remaining > 0:
            if self.index >= len(self.payloads):
                raise XlsError("SST 字符串不完整。")
            current = self.payloads[self.index]
            if self.offset >= len(current):
                # 跨记录：CONTINUE 开头的 1 个字节是后续字符的编码标志
                self.index += 1
                self.offset = 0
                if self.index >= len(self.payloads):
                    raise XlsError("SST 字符串不完整。")
                self.offset = 1
                wide = bool(self.payloads[self.index][0] & 0x01)
                continue
            available = len(current) - self.offset
            if wide:
                take_chars = min(remaining, available // 2)
                if take_chars <= 0:
                    self.index += 1
                    self.offset = 0
                    if self.index >= len(self.payloads):
                        raise XlsError("SST 字符串不完整。")
                    self.offset = 1
                    wide = bool(self.payloads[self.index][0] & 0x01)
                    continue
                raw = self.read_raw(take_chars * 2)
                chars.append(raw.decode("utf-16-le", errors="replace"))
            else:
                take_chars = min(remaining, available)
                raw = self.read_raw(take_chars)
                chars.append(raw.decode("latin-1"))
            remaining -= take_chars
        if runs:
            self.read_raw(runs * 4)
        if ext_size:
            self.read_raw(ext_size)
        return "".join(chars)


def _parse_sst(payloads: list[bytes]) -> list[str]:
    reader = _BoundaryReader(payloads)
    try:
        header = reader.read_raw(8)
        total, unique = struct.unpack_from("<II", header, 0)
    except (XlsError, struct.error):
        return []
    strings: list[str] = []
    for _ in range(min(unique, 10000)):
        try:
            strings.append(reader.read_string())
        except XlsError:
            break
    return strings


def _sheet_cells(rows: dict[int, dict[int, str]], row: int, col: int, value: str) -> None:
    if not value:
        return
    rows.setdefault(row, {})[col] = value


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:g}"


def read_xls_rows(path: str | Path) -> list[list[str]]:
    compound = _CompoundFile(Path(path).read_bytes())
    workbook = compound.stream("Workbook") if any(
        e["name"] == "Workbook" for e in compound.entries
    ) else compound.stream("Book")

    sst: list[str] = []
    pending_sst: list[bytes] = []
    in_sst = False
    boundsheets: list[tuple[int, str]] = []
    cells: dict[int, dict[int, str]] = {}
    sheet_index = -1
    in_globals = True
    in_sheet = False
    last_cell: tuple[int, int] | None = None

    for record_type, payload in _records(workbook):
        if record_type == 0x00FC:  # SST
            in_sst = True
            pending_sst = [payload]
            continue
        if record_type == 0x003C and in_sst:  # CONTINUE
            pending_sst.append(payload)
            continue
        if in_sst:
            sst = _parse_sst(pending_sst)
            in_sst = False
            pending_sst = []
        if record_type == 0x0809:  # BOF：offset 0 是版本，offset 2 是子流类型
            bof_type = struct.unpack_from("<H", payload, 2)[0]
            if bof_type == 0x0010:
                in_sheet = True
                sheet_index += 1
            continue
        if record_type == 0x000A:  # EOF
            if in_sheet:
                break
            continue
        if record_type == 0x0085:  # BOUNDSHEET
            position = struct.unpack_from("<I", payload, 0)[0]
            name, _ = _read_unicode_string(payload, 6, length_size=1)
            boundsheets.append((position, name))
            continue
        if not in_sheet or sheet_index != 0:
            continue
        if record_type in (0x00FD, 0x0204, 0x0203, 0x027E, 0x00BD, 0x0006, 0x0207):
            if record_type == 0x00FD:  # LABELSST
                row, col, _xf, isst = struct.unpack_from("<HHHI", payload, 0)
                text = sst[isst] if isst < len(sst) else ""
                _sheet_cells(cells, row, col, text)
            elif record_type == 0x0204:  # LABEL
                row, col, _xf = struct.unpack_from("<HHH", payload, 0)
                text, _ = _read_unicode_string(payload, 6)
                _sheet_cells(cells, row, col, text)
            elif record_type == 0x0203:  # NUMBER
                row, col, _xf = struct.unpack_from("<HHH", payload, 0)
                value = struct.unpack_from("<d", payload, 6)[0]
                _sheet_cells(cells, row, col, _format_number(value))
            elif record_type == 0x027E:  # RK
                row, col, _xf, rk = struct.unpack_from("<HHHI", payload, 0)
                _sheet_cells(cells, row, col, _format_number(_rk_value(rk)))
            elif record_type == 0x00BD:  # MULRK
                row, first_col = struct.unpack_from("<HH", payload, 0)
                count = (len(payload) - 6) // 6
                for index in range(count):
                    rk = struct.unpack_from("<I", payload, 4 + index * 6 + 2)[0]
                    _sheet_cells(cells, row, first_col + index, _format_number(_rk_value(rk)))
            elif record_type == 0x0006:  # FORMULA
                row, col, _xf = struct.unpack_from("<HHH", payload, 0)
                last_cell = (row, col)
                result = payload[6:14]
                if result[6:8] == b"\xff\xff":
                    kind = result[0]
                    if kind == 0:  # 字符串结果：内容在紧随的 STRING 记录里
                        continue
                    if kind == 1:
                        _sheet_cells(cells, row, col, "1" if result[2] else "0")
                    continue
                value = struct.unpack("<d", result)[0]
                _sheet_cells(cells, row, col, _format_number(value))
            elif record_type == 0x0207:  # STRING（公式的字符串结果）
                if last_cell is None:
                    continue
                text, _ = _read_unicode_string(payload, 0)
                _sheet_cells(cells, last_cell[0], last_cell[1], text)
                last_cell = None
            continue

    if in_sst:
        sst = _parse_sst(pending_sst)

    if not cells:
        raise XlsError("xls 文件里没有读到表格内容。")
    max_row = max(cells) + 1
    max_col = max(max(row) for row in cells.values()) + 1
    result: list[list[str]] = []
    for row_index in range(max_row):
        row_cells = cells.get(row_index, {})
        result.append([row_cells.get(col, "") for col in range(max_col)])
    return result
