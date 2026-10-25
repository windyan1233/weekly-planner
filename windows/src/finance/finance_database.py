"""记账模块自己的 SQLite 数据库。

独立文件（默认 ``%APPDATA%\\WeeklyPlanner\\finance.db``），独立版本号与迁移，
不读写日程库 ``planner.db``（首次创建时只做一次只读备份）。任何财务写入
都不会经过日程模块的连接。
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..database import DatabaseError

logger = logging.getLogger("weekly_planner.finance.db")

SCHEMA_VERSION = 2


def _create_statements() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            opening_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            system INTEGER NOT NULL DEFAULT 0
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_name ON accounts(name COLLATE NOCASE)",
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            occurred_on TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(occurred_on)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_transactions_kind ON transactions(kind, category)",
        """
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            to_account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            occurred_on TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            CHECK (from_account_id <> to_account_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_transfers_date ON transfers(occurred_on)",
        """
        CREATE TABLE IF NOT EXISTS monthly_reports (
            month TEXT PRIMARY KEY,
            opening_cents INTEGER NOT NULL,
            income_cents INTEGER NOT NULL,
            expense_cents INTEGER NOT NULL,
            closing_cents INTEGER NOT NULL,
            category_json TEXT NOT NULL DEFAULT '{}',
            account_json TEXT NOT NULL DEFAULT '[]',
            generated_at TEXT NOT NULL
        )
        """,
    ]


# 版本 -> 迁移语句；以后新增表/列时追加一个版本，旧库自动升级。
def _category_statements() -> list[str]:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS categories (
            key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            color TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            hidden INTEGER NOT NULL DEFAULT 0
        )
        """
    ]
    defaults = (
        ("food", "吃饭", "#E08A5C"),
        ("life", "生活", "#5B8DEF"),
        ("stationery", "文具", "#9B87E8"),
        ("game", "游戏", "#57AE84"),
        ("merch", "周边", "#DD7BA6"),
        ("tech", "科技", "#6A7BDB"),
    )
    for index, (key, label, color) in enumerate(defaults):
        statements.append(
            "INSERT OR IGNORE INTO categories(key, label, color, sort_order, hidden) "
            f"VALUES('{key}', '{label}', '{color}', {index}, 0)"
        )
    return statements


MIGRATIONS: dict[int, list[str]] = {
    1: _create_statements(),
    2: _category_statements(),
}


class FinanceDatabase:
    def __init__(self, path: str | Path, *, schedule_db_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.schedule_db_path = Path(schedule_db_path) if schedule_db_path else None
        self._connection: sqlite3.Connection | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._first_run_backup()
        try:
            self._connect()
            self._init_schema()
        except sqlite3.Error as exc:
            raise DatabaseError(f"财务数据库初始化失败：{exc}") from exc

    # ------------------------------------------------------------------
    # 连接与迁移
    # ------------------------------------------------------------------
    def _connect(self) -> None:
        connection = sqlite3.connect(str(self.path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        # autocommit：事务一律由 _Transaction 显式 BEGIN/COMMIT，避免隐式事务嵌套
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        # 写探测：目录只读时尽快给出明确错误
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ROLLBACK")
        except sqlite3.Error as exc:
            connection.close()
            raise DatabaseError(
                "财务数据目录不可写，记账数据无法保存。\n"
                f"目录：{self.path.parent}\n原因：{exc}"
            ) from exc
        self._connection = connection

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connect()
        assert self._connection is not None
        return self._connection

    def _user_version(self) -> int:
        row = self.connection.execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row else 0

    def _init_schema(self) -> None:
        current = self._user_version()
        if current >= SCHEMA_VERSION:
            return
        if current > 0:
            self._backup_before_migration(current)
        with self.transaction():
            for version in range(current + 1, SCHEMA_VERSION + 1):
                for statement in MIGRATIONS.get(version, []):
                    self.connection.execute(statement)
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        logger.info("财务数据库结构版本：%s -> %s", current, SCHEMA_VERSION)

    def _first_run_backup(self) -> None:
        """首次创建财务库时，对现有日程库做一次只读备份。"""
        if self.path.exists() and self.path.stat().st_size > 0:
            return
        schedule = self.schedule_db_path
        if not schedule or not schedule.exists():
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.path.parent / f"planner.before-finance-{stamp}.db"
        try:
            shutil.copy2(schedule, target)
            logger.info("记账首次启用，已备份日程数据库：%s", target)
        except OSError as exc:  # 备份失败不阻止记账初始化
            logger.warning("备份日程数据库失败：%s", exc)

    def _backup_before_migration(self, current_version: int) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.path.parent / f"finance.before-v{current_version}-{stamp}.db"
        try:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            shutil.copy2(self.path, target)
            logger.info("财务数据库升级前备份：%s", target)
        except OSError as exc:
            raise DatabaseError(f"财务数据库升级前备份失败：{exc}") from exc

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        try:
            return list(self.connection.execute(sql, params))
        except sqlite3.Error as exc:
            raise DatabaseError(f"财务数据读取失败：{exc}") from exc

    def query_one(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return None if row is None else row[0]

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> int:
        try:
            cursor = self.connection.execute(sql, params)
            return cursor.lastrowid or 0
        except sqlite3.Error as exc:
            raise DatabaseError(f"财务数据保存失败：{exc}") from exc

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        try:
            self.connection.executemany(sql, list(rows))
        except sqlite3.Error as exc:
            raise DatabaseError(f"财务数据保存失败：{exc}") from exc

    def transaction(self) -> "_Transaction":
        return _Transaction(self)

    # ------------------------------------------------------------------
    # 设置
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ------------------------------------------------------------------
    # 备份 / 恢复
    # ------------------------------------------------------------------
    def backup_to(self, target: str | Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = sqlite3.connect(str(target))
        try:
            self.connection.backup(backup)
            backup.execute("PRAGMA user_version = %d" % self._user_version())
        finally:
            backup.close()
        return target

    @staticmethod
    def validate_backup(path: str | Path) -> int:
        candidate = Path(path)
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise DatabaseError("备份文件不存在或为空。")
        try:
            connection = sqlite3.connect(f"file:{candidate}?mode=ro", uri=True)
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise DatabaseError(f"备份文件无法读取：{exc}") from exc
        required = {"settings", "accounts", "transactions", "transfers"}
        if not required.issubset(tables):
            raise DatabaseError("备份文件不是有效的记账数据。")
        if version > SCHEMA_VERSION:
            raise DatabaseError("备份来自更新版本的记账模块，当前版本无法恢复。")
        return version

    def restore_from(self, path: str | Path) -> None:
        FinanceDatabase.validate_backup(path)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety = self.path.parent / f"finance.before-restore-{stamp}.db"
        try:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            if self.path.exists():
                shutil.copy2(self.path, safety)
            for suffix in ("-wal", "-shm"):
                extra = Path(str(self.path) + suffix)
                if extra.exists():
                    extra.unlink()
            shutil.copy2(path, self.path)
        except OSError as exc:
            raise DatabaseError(f"恢复记账数据失败：{exc}") from exc
        self._connect()
        self._init_schema()
        logger.info("已从备份恢复记账数据：%s（恢复前副本 %s）", path, safety)

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.commit()
            except sqlite3.Error:
                pass
            self._connection.close()
            self._connection = None


class _Transaction:
    """上下文管理器：成功提交，异常回滚，避免部分写入。"""

    def __init__(self, db: FinanceDatabase) -> None:
        self.db = db
        self._started = False

    def __enter__(self) -> "_Transaction":
        try:
            self.db.connection.execute("BEGIN IMMEDIATE")
            self._started = True
        except sqlite3.Error as exc:
            raise DatabaseError(f"财务数据写入失败：{exc}") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        connection = self.db.connection
        try:
            if exc_type is None:
                connection.commit()
            else:
                connection.rollback()
        except sqlite3.Error:
            connection.rollback()
        self._started = False
        return False
