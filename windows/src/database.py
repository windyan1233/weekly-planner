"""SQLite 持久层。

设计要点
--------
* 全部数据的唯一权威来源，进程内所有写操作都走事务并加锁。
* 所有 sqlite 异常统一包装成 :class:`DatabaseError`，附带中文说明，UI 层据此
  给出明确提示，而不是静默失败。
* 提供备份 / 恢复 / CSV 导入导出，方便用户自行迁移。
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    due_at          TEXT    NOT NULL,
    category        TEXT    NOT NULL DEFAULT '学习',
    priority        TEXT    NOT NULL DEFAULT 'normal',
    status          TEXT    NOT NULL DEFAULT 'todo',
    remind_due      INTEGER NOT NULL DEFAULT 1,
    notes           TEXT    NOT NULL DEFAULT '',
    completed_at    TEXT,
    overdue_notified INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS plan_times (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id             INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    plan_at             TEXT    NOT NULL,
    label               TEXT    NOT NULL DEFAULT '',
    remind_enabled      INTEGER NOT NULL DEFAULT 0,
    remind_lead_minutes INTEGER NOT NULL DEFAULT 10,
    done                INTEGER NOT NULL DEFAULT 0,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    end_at              TEXT,
    remind_start        INTEGER NOT NULL DEFAULT 1,
    remind_end          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_plans_task ON plan_times(task_id);
CREATE INDEX IF NOT EXISTS idx_plans_at ON plan_times(plan_at);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL,
    plan_id     INTEGER REFERENCES plan_times(id) ON DELETE CASCADE,
    fire_at     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    fired_at    TEXT,
    snooze_count INTEGER NOT NULL DEFAULT 0,
    anchor_at   TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, fire_at);
CREATE INDEX IF NOT EXISTS idx_reminders_task ON reminders(task_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reminders_identity
    ON reminders(task_id, kind, IFNULL(plan_id, 0), anchor_at)
    WHERE status IN ('pending', 'sent');

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 课程表（v2）：课程 + 每次课；课程不参与任务与提醒
CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    teacher     TEXT    NOT NULL DEFAULT '',
    location    TEXT    NOT NULL DEFAULT '',
    descriptor  TEXT    NOT NULL DEFAULT '',
    color       TEXT    NOT NULL DEFAULT '#6C8AE4',
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS course_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id     INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    day           TEXT    NOT NULL,
    start_minutes INTEGER NOT NULL,
    end_minutes   INTEGER NOT NULL,
    skipped       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_course_sessions_day ON course_sessions(day);
CREATE INDEX IF NOT EXISTS idx_course_sessions_course ON course_sessions(course_id);
"""

# 旧库升级：按需给 plan_times 补列（用 PRAGMA table_info 判断，可重复执行）
PLAN_TIME_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("end_at", "ALTER TABLE plan_times ADD COLUMN end_at TEXT"),
    ("remind_start", "ALTER TABLE plan_times ADD COLUMN remind_start INTEGER NOT NULL DEFAULT 1"),
    ("remind_end", "ALTER TABLE plan_times ADD COLUMN remind_end INTEGER NOT NULL DEFAULT 0"),
)


class DatabaseError(RuntimeError):
    """数据库操作失败（带用户可读说明）。"""

    def __init__(self, message: str, *, detail: str = "", operation: str = "") -> None:
        super().__init__(message)
        self.detail = detail
        self.operation = operation

    def user_message(self) -> str:
        if self.detail:
            return f"{self}\n\n详细信息：{self.detail}"
        return str(self)


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Database:
    """线程安全的 SQLite 封装。"""

    def __init__(self, path: str | Path, *, create: bool = True) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        if create:
            parent = self.path.parent
            if not parent.exists():
                try:
                    parent.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise DatabaseError(
                        f"无法创建数据目录：{parent}",
                        detail=str(exc),
                        operation="mkdir",
                    ) from exc
        self._connect()
        self._init_schema()

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def _connect(self) -> None:
        try:
            conn = sqlite3.connect(
                str(self.path),
                isolation_level=None,       # 手动控制事务
                check_same_thread=False,
                timeout=10.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"无法打开数据库文件：{self.path}",
                detail=str(exc),
                operation="connect",
            ) from exc
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("数据库连接已关闭", operation="connection")
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 表和事务
    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        with self._lock:
            try:
                version = self.connection.execute("PRAGMA user_version").fetchone()[0]
                self.connection.executescript(SCHEMA_SQL)
                self._migrate_schema()
                if version < SCHEMA_VERSION:
                    self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                # 真正试一次写事务：表都存在时 CREATE IF NOT EXISTS 不会触发写入，
                # 只有这样才能尽早发现「数据库只读 / 目录不可写」，而不是等到用户保存时炸
                self.connection.execute("BEGIN IMMEDIATE")
                self.connection.execute("ROLLBACK")
            except sqlite3.Error as exc:
                try:
                    self.connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                message = "初始化数据库失败：数据库文件可能已损坏或不可写。"
                if "readonly" in str(exc).lower():
                    message = (
                        "数据目录不可写，程序无法保存数据。\n"
                        "请确认程序以当前 Windows 用户身份正常启动（不要从受限环境运行），"
                        "并检查安全软件是否拦截了对该目录的写入。"
                    )
                raise DatabaseError(
                    message,
                    detail=f"{exc}（文件：{self.path}）",
                    operation="init_schema",
                ) from exc

    def _migrate_schema(self) -> None:
        """给旧库补齐新增列（``PRAGMA table_info`` 检查后 ``ALTER TABLE``）。

        旧数据：``end_at`` 保持 NULL（表示没有结束时间）；``remind_start`` 回填成
        原来的 ``remind_enabled``，这样升级后旧任务的提醒行为不会突然变化。
        """
        columns = {
            str(row["name"]) for row in self.connection.execute("PRAGMA table_info(plan_times)")
        }
        added: set[str] = set()
        for name, ddl in PLAN_TIME_MIGRATIONS:
            if name in columns:
                continue
            self.connection.execute(ddl)
            added.add(name)
        if "remind_start" in added and "remind_enabled" in columns:
            self.connection.execute("UPDATE plan_times SET remind_start = remind_enabled")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """事务上下文；嵌套调用使用 SAVEPOINT。"""
        with self._lock:
            conn = self.connection
            depth = getattr(self, "_tx_depth", 0)
            self._tx_depth = depth + 1
            try:
                if depth == 0:
                    conn.execute("BEGIN IMMEDIATE")
                else:
                    conn.execute(f"SAVEPOINT sp_{depth}")
                yield conn
                if depth == 0:
                    conn.execute("COMMIT")
                else:
                    conn.execute(f"RELEASE sp_{depth}")
            except sqlite3.Error as exc:
                try:
                    if depth == 0:
                        conn.execute("ROLLBACK")
                    else:
                        conn.execute(f"ROLLBACK TO sp_{depth}")
                except sqlite3.Error:
                    pass
                raise DatabaseError(
                    "数据库写入失败，本次修改没有保存。请检查磁盘空间或文件权限。",
                    detail=str(exc),
                    operation="transaction",
                ) from exc
            except Exception:
                try:
                    if depth == 0:
                        conn.execute("ROLLBACK")
                    else:
                        conn.execute(f"ROLLBACK TO sp_{depth}")
                except sqlite3.Error:
                    pass
                raise
            finally:
                self._tx_depth = depth

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return list(self.connection.execute(sql, tuple(params)).fetchall())
            except sqlite3.Error as exc:
                raise DatabaseError(
                    "读取数据库失败。",
                    detail=str(exc),
                    operation="query",
                ) from exc

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return row[0] if row is not None else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                return self.connection.execute(sql, tuple(params))
            except sqlite3.Error as exc:
                raise DatabaseError(
                    "数据库写入失败，本次修改没有保存。",
                    detail=str(exc),
                    operation="execute",
                ) from exc

    def insert(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            return int(cursor.lastrowid or 0)

    def executemany(self, sql: str, params: Iterable[Sequence[Any]]) -> None:
        with self.transaction() as conn:
            conn.executemany(sql, list(params))

    # ------------------------------------------------------------------
    # 键值设置
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return default

    def set_setting(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, payload),
            )

    def all_settings(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for row in self.query("SELECT key, value FROM settings"):
            try:
                result[row["key"]] = json.loads(row["value"])
            except (TypeError, ValueError):
                continue
        return result

    # ------------------------------------------------------------------
    # 备份 / 恢复
    # ------------------------------------------------------------------
    def backup_to(self, target: str | Path) -> Path:
        target_path = Path(target)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                dest = sqlite3.connect(str(target_path))
                try:
                    self.connection.backup(dest)
                finally:
                    dest.close()
        except (sqlite3.Error, OSError) as exc:
            raise DatabaseError(
                f"备份数据库失败：{target_path}",
                detail=str(exc),
                operation="backup",
            ) from exc
        return target_path

    @staticmethod
    def validate_backup(path: str | Path) -> tuple[bool, str]:
        """检查文件看起来是不是本程序的数据库。"""
        candidate = Path(path)
        if not candidate.exists() or candidate.stat().st_size == 0:
            return False, "文件不存在或为空。"
        try:
            conn = sqlite3.connect(str(candidate))
            try:
                names = {
                    row[0]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                check = conn.execute("PRAGMA integrity_check").fetchone()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return False, f"不是有效的 SQLite 数据库：{exc}"
        if check and str(check[0]).lower() != "ok":
            return False, f"数据库完整性检查未通过：{check[0]}"
        missing = {"tasks", "plan_times", "reminders", "settings"} - names
        if missing:
            return False, "备份文件缺少数据表：" + "、".join(sorted(missing))
        return True, ""

    def restore_from(self, source: str | Path) -> None:
        source_path = Path(source)
        ok, reason = self.validate_backup(source_path)
        if not ok:
            raise DatabaseError(f"无法恢复：{reason}", operation="restore")
        with self._lock:
            try:
                try:
                    self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except sqlite3.Error:
                    pass
                if self.path.exists():
                    shutil.copy2(self.path, self.path.with_suffix(".before-restore.db"))
                self.connection.close()
                self._conn = None
                shutil.copy2(source_path, self.path)
            except (sqlite3.Error, OSError) as exc:
                raise DatabaseError(
                    "恢复数据库失败，原数据未被覆盖。",
                    detail=str(exc),
                    operation="restore",
                ) from exc
            finally:
                if self._conn is None:
                    self._connect()
                self._init_schema()

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------
    @staticmethod
    def _plans_to_text(plans: Iterable[Any]) -> str:
        """计划时间列格式：``开始|说明|提前分钟|结束|提醒开始|提醒结束``。

        后三段是新增的（旧版 CSV 只有前三段），读取时缺失就按旧行为处理。
        """
        chunks = []
        for plan in plans:
            remark = plan.label.replace("|", "／")
            end_at = plan.end_at.strftime("%Y-%m-%d %H:%M") if plan.end_at else ""
            chunks.append(
                "|".join(
                    [
                        plan.plan_at.strftime("%Y-%m-%d %H:%M"),
                        remark,
                        str(plan.remind_lead_minutes),
                        end_at,
                        "1" if plan.remind_start else "0",
                        "1" if plan.remind_end else "0",
                    ]
                )
            )
        return "; ".join(chunks)

    def export_csv(self, path: str | Path) -> int:
        """导出所有任务（一行一个任务，计划时间合并在一列）。"""
        from .models import PRIORITY_LABELS, STATUS_LABELS

        rows = self.query(
            "SELECT * FROM tasks ORDER BY due_at ASC, id ASC"
        )
        plans: dict[int, list[sqlite3.Row]] = {}
        for row in self.query("SELECT * FROM plan_times ORDER BY plan_at ASC"):
            plans.setdefault(row["task_id"], []).append(row)

        headers = [
            "任务名称",
            "任务说明",
            "截止时间",
            "分类",
            "优先级",
            "状态",
            "截止前一天提醒",
            "计划时间",
            "备注",
        ]

        class _Plan:
            def __init__(self, row: sqlite3.Row) -> None:
                self.plan_at = datetime.strptime(row["plan_at"], "%Y-%m-%d %H:%M")
                self.label = row["label"] or ""
                self.remind_lead_minutes = row["remind_lead_minutes"]
                self.end_at = (
                    datetime.strptime(row["end_at"], "%Y-%m-%d %H:%M") if row["end_at"] else None
                )
                self.remind_start = bool(row["remind_start"])
                self.remind_end = bool(row["remind_end"])

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                for row in rows:
                    task_plans = [_Plan(p) for p in plans.get(row["id"], [])]
                    writer.writerow(
                        [
                            row["title"],
                            (row["description"] or "").replace("\n", "\\n"),
                            row["due_at"],
                            row["category"],
                            PRIORITY_LABELS.get(row["priority"], row["priority"]),
                            STATUS_LABELS.get(row["status"], row["status"]),
                            "是" if row["remind_due"] else "否",
                            self._plans_to_text(task_plans),
                            (row["notes"] or "").replace("\n", "\\n"),
                        ]
                    )
        except OSError as exc:
            raise DatabaseError(f"导出 CSV 失败：{path}", detail=str(exc), operation="export_csv") from exc
        return len(rows)

    @staticmethod
    def _parse_priority(text: str) -> str:
        from .models import PRIORITIES

        for key, label in PRIORITIES:
            if text.strip() in (key, label):
                return key
        return "normal"

    @staticmethod
    def _parse_status(text: str) -> str:
        from .models import STATUSES

        for key, label in STATUSES:
            if text.strip() in (key, label):
                return key
        return "todo"

    def import_csv(self, path: str | Path) -> dict[str, int]:
        """导入 CSV；同名的任务不会被去重，每次导入都会新增记录。"""
        from .time_utils import format_dt, parse_dt

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                records = list(reader)
        except OSError as exc:
            raise DatabaseError(f"读取 CSV 失败：{path}", detail=str(exc), operation="import_csv") from exc
        except UnicodeDecodeError as exc:
            raise DatabaseError(
                "CSV 编码无法识别，请使用 UTF-8 编码。",
                detail=str(exc),
                operation="import_csv",
            ) from exc

        if records and not {"任务名称", "截止时间"}.issubset(set(records[0].keys())):
            raise DatabaseError(
                "CSV 缺少必要的列（任务名称、截止时间）。",
                operation="import_csv",
            )

        imported = 0
        plan_count = 0
        skipped = 0
        now_text = _now_text()
        with self.transaction() as conn:
            for record in records:
                title = (record.get("任务名称") or "").strip()
                due_raw = (record.get("截止时间") or "").strip()
                if not title or not due_raw:
                    skipped += 1
                    continue
                try:
                    due_at = parse_dt(due_raw.replace("/", "-"))
                except ValueError:
                    skipped += 1
                    continue
                status = self._parse_status(record.get("状态") or "")
                cursor = conn.execute(
                    "INSERT INTO tasks(title, description, due_at, category, priority, status,"
                    " remind_due, notes, completed_at, overdue_notified, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,0,?,?)",
                    (
                        title,
                        (record.get("任务说明") or "").replace("\\n", "\n"),
                        format_dt(due_at),
                        (record.get("分类") or "学习").strip() or "学习",
                        self._parse_priority(record.get("优先级") or ""),
                        status,
                        # 只认「是/否/1/0」；空值按默认开启处理
                        "否" not in (record.get("截止前一天提醒") or "是")
                        and "0" != (record.get("截止前一天提醒") or "").strip(),
                        (record.get("备注") or "").replace("\\n", "\n"),
                        format_dt(datetime.now()) if status == "done" else None,
                        now_text,
                        now_text,
                    ),
                )
                task_id = int(cursor.lastrowid or 0)
                imported += 1
                plans_raw = (record.get("计划时间") or "").strip()
                if not plans_raw:
                    continue
                for index, chunk in enumerate([c.strip() for c in plans_raw.split(";") if c.strip()]):
                    parts = chunk.split("|")
                    try:
                        plan_at = parse_dt(parts[0].strip())
                    except ValueError:
                        continue
                    label = parts[1].strip() if len(parts) > 1 else ""
                    try:
                        lead = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip() else 0
                    except ValueError:
                        lead = 0
                    end_at = None
                    if len(parts) > 3 and parts[3].strip():
                        try:
                            end_at = parse_dt(parts[3].strip())
                        except ValueError:
                            end_at = None
                        if end_at is not None and end_at <= plan_at:
                            end_at = None
                    # 旧 CSV 没有第 5 段：沿用原来的「提前分钟 > 0 才有开始提醒」
                    if len(parts) > 4 and parts[4].strip():
                        remind_start = parts[4].strip().lower() in ("1", "是", "true", "yes")
                    else:
                        remind_start = lead > 0
                    remind_end = (
                        end_at is not None
                        and len(parts) > 5
                        and parts[5].strip().lower() in ("1", "是", "true", "yes")
                    )
                    conn.execute(
                        "INSERT INTO plan_times(task_id, plan_at, end_at, label, remind_enabled,"
                        " remind_start, remind_end, remind_lead_minutes, done, sort_order)"
                        " VALUES (?,?,?,?,?,?,?,?,0,?)",
                        (
                            task_id,
                            format_dt(plan_at),
                            format_dt(end_at) if end_at is not None else None,
                            label,
                            1 if remind_start else 0,
                            1 if remind_start else 0,
                            1 if remind_end else 0,
                            lead if lead > 0 else 10,
                            index,
                        ),
                    )
                    plan_count += 1
        return {"tasks": imported, "plans": plan_count, "skipped": skipped}

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        return {
            "tasks": int(self.scalar("SELECT COUNT(*) FROM tasks") or 0),
            "plans": int(self.scalar("SELECT COUNT(*) FROM plan_times") or 0),
            "reminders": int(self.scalar("SELECT COUNT(*) FROM reminders") or 0),
            "pending_reminders": int(
                self.scalar("SELECT COUNT(*) FROM reminders WHERE status = 'pending'") or 0
            ),
        }

    def file_size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0
