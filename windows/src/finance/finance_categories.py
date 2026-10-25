"""支出分类：默认六个 + 「自定义分类版」里可增改隐藏。

分类以稳定 key 保存（历史账目引用 key），名称可随时改；隐藏只是不再出现在
新记账的选择里，历史账目和月报仍然按原分类统计，保证合计始终等于总支出。
"""

from __future__ import annotations

from .finance_database import FinanceDatabase
from .finance_models import (
    CATEGORIES,
    CATEGORY_LABELS,
    CUSTOM_CATEGORY_COLORS,
    Category,
    FinanceError,
    set_category_labels,
)

MAX_LABEL_LENGTH = 12


class CategoryRepository:
    def __init__(self, db: FinanceDatabase) -> None:
        self.db = db
        self.ensure_seeded()
        self.refresh_labels()

    # ------------------------------------------------------------------
    def ensure_seeded(self) -> None:
        count = int(self.db.scalar("SELECT COUNT(*) FROM categories") or 0)
        if count:
            return
        with self.db.transaction():
            for index, (key, label, color, _note) in enumerate(CATEGORIES):
                self.db.execute(
                    "INSERT OR IGNORE INTO categories(key, label, color, sort_order, hidden) "
                    "VALUES(?, ?, ?, ?, 0)",
                    (key, label, color, index),
                )

    def refresh_labels(self) -> None:
        set_category_labels({item.key: item.label for item in self.list()})

    # ------------------------------------------------------------------
    def list(self, *, include_hidden: bool = True) -> list[Category]:
        sql = "SELECT key, label, color, sort_order, hidden FROM categories"
        if not include_hidden:
            sql += " WHERE hidden = 0"
        sql += " ORDER BY sort_order, key"
        return [
            Category(
                key=row["key"],
                label=row["label"],
                color=row["color"],
                sort_order=int(row["sort_order"]),
                hidden=bool(row["hidden"]),
            )
            for row in self.db.query(sql)
        ]

    def active(self) -> list[Category]:
        return self.list(include_hidden=False)

    def get(self, key: str) -> Category:
        row = self.db.query_one(
            "SELECT key, label, color, sort_order, hidden FROM categories WHERE key = ?",
            (key,),
        )
        if row is None:
            raise FinanceError("这个支出分类不存在。")
        return Category(
            key=row["key"],
            label=row["label"],
            color=row["color"],
            sort_order=int(row["sort_order"]),
            hidden=bool(row["hidden"]),
        )

    def exists(self, key: str) -> bool:
        return self.db.query_one("SELECT 1 FROM categories WHERE key = ?", (key,)) is not None

    def note(self, key: str) -> str:
        for item in CATEGORIES:
            if item[0] == key:
                return item[3]
        return ""

    def usage(self, key: str) -> int:
        return int(
            self.db.scalar("SELECT COUNT(*) FROM transactions WHERE category = ?", (key,)) or 0
        )

    # ------------------------------------------------------------------
    def _check_label(self, label: str, exclude_key: str | None = None) -> str:
        clean = (label or "").strip()
        if not clean:
            raise FinanceError("分类名称不能为空。")
        if len(clean) > MAX_LABEL_LENGTH:
            raise FinanceError(f"分类名称最多 {MAX_LABEL_LENGTH} 个字。")
        for item in self.list():
            if item.label.lower() == clean.lower() and item.key != exclude_key:
                raise FinanceError(f"已经有一个叫「{clean}」的分类了。")
        return clean

    def add(self, label: str, color: str | None = None) -> str:
        clean = self._check_label(label)
        if color is None:
            used = {item.color for item in self.list()}
            color = next((value for value in CUSTOM_CATEGORY_COLORS if value not in used), CUSTOM_CATEGORY_COLORS[0])
        serial = int(self.db.scalar("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories") or 0)
        key = f"cat_{serial + 1}"
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO categories(key, label, color, sort_order, hidden) VALUES(?, ?, ?, ?, 0)",
                (key, clean, color, serial),
            )
        self.refresh_labels()
        return key

    def rename(self, key: str, label: str) -> None:
        self.get(key)
        clean = self._check_label(label, exclude_key=key)
        with self.db.transaction():
            self.db.execute("UPDATE categories SET label = ? WHERE key = ?", (clean, key))
        self.refresh_labels()

    def set_hidden(self, key: str, hidden: bool) -> None:
        self.get(key)
        if hidden and len(self.active()) <= 1:
            raise FinanceError("至少要保留一个可用的支出分类。")
        with self.db.transaction():
            self.db.execute(
                "UPDATE categories SET hidden = ? WHERE key = ?", (1 if hidden else 0, key)
            )
        self.refresh_labels()

    # ------------------------------------------------------------------
    def labels(self) -> dict[str, str]:
        return {item.key: item.label for item in self.list()}
