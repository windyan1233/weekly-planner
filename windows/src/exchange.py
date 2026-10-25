"""Windows ↔ Android 的 JSON 数据互通。

统一格式（version 1）：
{
  "format": "weekly-planner-exchange",
  "version": 1,
  "source": "windows" | "android",
  "tasks": [...], "plans": [...], "accounts": [...], "transactions": [...],
  "transfers": [...], "reports": [...], "courses": [...], "courseSessions": [...]
}

金额一律用「分」；时间一律用 epoch 毫秒（本地时区换算）。
导入是「整体替换」：会清空当前任务、计划时间、课程、账目、资金分区和月报，
然后写入 JSON 里的数据。
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

FORMAT = "weekly-planner-exchange"
VERSION = 1


# ---------------------------------------------------------------------------
# 时间转换
# ---------------------------------------------------------------------------
def _dt_to_millis(text: str | None) -> int | None:
    if not text:
        return None
    try:
        value = datetime.fromisoformat(str(text).strip())
    except ValueError:
        return None
    return int(value.timestamp() * 1000)


def _millis_to_dt(value: Any) -> str:
    if value in (None, ""):
        return ""
    return datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d %H:%M")


def _date_to_millis(text: str | None) -> int | None:
    if not text:
        return None
    try:
        value = date.fromisoformat(str(text).strip())
    except ValueError:
        return None
    return int(datetime.combine(value, time.min).timestamp() * 1000)


def _millis_to_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    return datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _has_table(db, name: str) -> bool:
    row = db.query_one(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    )
    return row is not None


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
def export_payload(planner_db, finance_db) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "source": "windows",
        "app": "weekly-planner",
        "exportedAt": int(datetime.now().timestamp() * 1000),
    }

    tasks = []
    for row in planner_db.query("SELECT * FROM tasks ORDER BY id"):
        notes = row["notes"] or row["description"] or ""
        tasks.append(
            {
                "id": int(row["id"]),
                "title": row["title"],
                "note": notes,
                "kind": row["category"] or "学习",
                "priority": row["priority"] or "normal",
                "dueAt": _dt_to_millis(row["due_at"]),
                "done": row["status"] == "done",
                "createdAt": _dt_to_millis(row["created_at"]) or 0,
                "updatedAt": _dt_to_millis(row["updated_at"]) or 0,
            }
        )
    payload["tasks"] = tasks

    payload["plans"] = [
        {
            "id": int(row["id"]),
            "taskId": int(row["task_id"]),
            "planAt": _dt_to_millis(row["plan_at"]) or 0,
        }
        for row in planner_db.query("SELECT * FROM plan_times ORDER BY id")
    ]

    if _has_table(planner_db, "courses"):
        payload["courses"] = [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "teacher": row["teacher"] or "",
                "location": row["location"] or "",
                "descriptor": row["descriptor"] or "",
                "color": row["color"] or "#6C8AE4",
                "createdAt": _dt_to_millis(row["created_at"]) or 0,
            }
            for row in planner_db.query("SELECT * FROM courses ORDER BY id")
        ]
    else:
        payload["courses"] = []

    if _has_table(planner_db, "course_sessions"):
        payload["courseSessions"] = [
            {
                "id": int(row["id"]),
                "courseId": int(row["course_id"]),
                "day": row["day"],
                "startMinutes": int(row["start_minutes"]),
                "endMinutes": int(row["end_minutes"]),
            }
            for row in planner_db.query("SELECT * FROM course_sessions ORDER BY id")
        ]
    else:
        payload["courseSessions"] = []

    accounts = list(finance_db.query("SELECT * FROM accounts ORDER BY id"))
    payload["accounts"] = [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "openingCents": int(row["opening_cents"]),
            "sortOrder": index,
            "archived": bool(row["archived"]),
            "createdAt": _dt_to_millis(row["created_at"]) or 0,
        }
        for index, row in enumerate(accounts)
    ]

    payload["transactions"] = [
        {
            "id": int(row["id"]),
            "type": row["kind"],
            "amountCents": int(row["amount_cents"]),
            "categoryKey": row["category"] or "",
            "accountId": int(row["account_id"]),
            "title": row["title"] or "",
            "note": row["note"] or "",
            "occurredAt": _date_to_millis(row["occurred_on"]) or 0,
            "createdAt": _dt_to_millis(row["created_at"]) or 0,
        }
        for row in finance_db.query("SELECT * FROM transactions ORDER BY id")
    ]

    payload["transfers"] = [
        {
            "id": int(row["id"]),
            "fromAccountId": int(row["from_account_id"]),
            "toAccountId": int(row["to_account_id"]),
            "amountCents": int(row["amount_cents"]),
            "note": row["note"] or "",
            "occurredAt": _date_to_millis(row["occurred_on"]) or 0,
            "createdAt": _dt_to_millis(row["created_at"]) or 0,
        }
        for row in finance_db.query("SELECT * FROM transfers ORDER BY id")
    ]

    payload["reports"] = [
        {
            "month": row["month"],
            "incomeCents": int(row["income_cents"]),
            "expenseCents": int(row["expense_cents"]),
            "openingCents": int(row["opening_cents"]),
            "closingCents": int(row["closing_cents"]),
            "categoryJson": row["category_json"] or "{}",
            "createdAt": _dt_to_millis(row["generated_at"]) or 0,
        }
        for row in finance_db.query("SELECT * FROM monthly_reports ORDER BY month")
    ]
    return payload


def export_to_file(planner_db, finance_db, path: Path) -> dict[str, Any]:
    payload = export_payload(planner_db, finance_db)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# 导入
# ---------------------------------------------------------------------------
def import_payload(planner_db, finance_db, payload: dict[str, Any]) -> dict[str, int]:
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError("不是一周日程的互通 JSON 文件。")
    if int(payload.get("version", 0)) > VERSION:
        raise ValueError("JSON 版本比当前程序新，请升级程序后再导入。")

    tasks = payload.get("tasks") or []
    plans = payload.get("plans") or []
    courses = payload.get("courses") or []
    course_sessions = payload.get("courseSessions") or []
    accounts = payload.get("accounts") or []
    transactions = payload.get("transactions") or []
    transfers = payload.get("transfers") or []
    reports = payload.get("reports") or []

    known_task_ids = {int(item["id"]) for item in tasks}

    with planner_db.transaction() as connection:
        connection.execute("DELETE FROM reminders")
        connection.execute("DELETE FROM plan_times")
        connection.execute("DELETE FROM tasks")
        if _has_table(planner_db, "course_sessions"):
            connection.execute("DELETE FROM course_sessions")
        if _has_table(planner_db, "courses"):
            connection.execute("DELETE FROM courses")

        for item in tasks:
            due_at = _millis_to_dt(item.get("dueAt")) or _millis_to_dt(item.get("createdAt"))
            due_at = due_at or _now_iso()
            if not item.get("dueAt"):
                due_at = _millis_to_dt(item.get("createdAt")) or _now_iso()
            status = "done" if item.get("done") else "todo"
            completed_at = _millis_to_dt(item.get("updatedAt")) if item.get("done") else None
            note = item.get("note") or ""
            connection.execute(
                """
                INSERT INTO tasks (id, title, description, due_at, category, priority, status,
                                   remind_due, notes, completed_at, overdue_notified, created_at, updated_at)
                VALUES (?, ?, '', ?, ?, ?, ?, 1, ?, ?, 0, ?, ?)
                """,
                (
                    int(item["id"]),
                    item.get("title") or "未命名任务",
                    due_at,
                    item.get("kind") or "学习",
                    item.get("priority") or "normal",
                    status,
                    note,
                    completed_at,
                    _millis_to_dt(item.get("createdAt")) or _now_iso(),
                    _millis_to_dt(item.get("updatedAt")) or _now_iso(),
                ),
            )

        for index, item in enumerate(plans):
            task_id = int(item.get("taskId", 0))
            if task_id not in known_task_ids:
                continue
            connection.execute(
                """
                INSERT INTO plan_times (id, task_id, plan_at, label, remind_enabled,
                                        remind_lead_minutes, done, sort_order)
                VALUES (?, ?, ?, '', 0, 10, 0, ?)
                """,
                (
                    int(item["id"]),
                    task_id,
                    _millis_to_dt(item.get("planAt")) or _now_iso(),
                    index,
                ),
            )

        for item in courses:
            if not _has_table(planner_db, "courses"):
                break
            connection.execute(
                "INSERT INTO courses (id, name, teacher, location, descriptor, color, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    int(item["id"]),
                    item.get("name") or "未命名课程",
                    item.get("teacher") or "",
                    item.get("location") or "",
                    item.get("descriptor") or "",
                    item.get("color") or "#6C8AE4",
                    _millis_to_dt(item.get("createdAt")) or _now_iso(),
                ),
            )

        if _has_table(planner_db, "course_sessions"):
            for item in course_sessions:
                connection.execute(
                    "INSERT INTO course_sessions (id, course_id, day, start_minutes, end_minutes, skipped) "
                    "VALUES (?, ?, ?, ?, ?, 0)",
                    (
                        int(item["id"]),
                        int(item["courseId"]),
                        item["day"],
                        int(item["startMinutes"]),
                        int(item["endMinutes"]),
                    ),
                )

    with finance_db.transaction():
        finance_db.execute("DELETE FROM transactions")
        finance_db.execute("DELETE FROM transfers")
        finance_db.execute("DELETE FROM monthly_reports")
        finance_db.execute("DELETE FROM accounts")

        for item in accounts:
            finance_db.execute(
                "INSERT INTO accounts (id, name, note, opening_cents, created_at, archived, system) "
                "VALUES (?, ?, '', ?, ?, ?, 0)",
                (
                    int(item["id"]),
                    item.get("name") or "默认",
                    int(item.get("openingCents") or 0),
                    _millis_to_dt(item.get("createdAt")) or _now_iso(),
                    1 if item.get("archived") else 0,
                ),
            )

        for item in transactions:
            finance_db.execute(
                """
                INSERT INTO transactions (id, kind, amount_cents, occurred_on, title, category,
                                          account_id, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(item["id"]),
                    item.get("type") or "expense",
                    int(item.get("amountCents") or 0),
                    _millis_to_date(item.get("occurredAt")),
                    item.get("title") or "",
                    item.get("categoryKey") or "",
                    int(item.get("accountId") or 0),
                    item.get("note") or "",
                    _millis_to_dt(item.get("createdAt")) or _now_iso(),
                    _millis_to_dt(item.get("createdAt")) or _now_iso(),
                ),
            )

        for item in transfers:
            finance_db.execute(
                """
                INSERT INTO transfers (id, from_account_id, to_account_id, amount_cents,
                                       occurred_on, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(item["id"]),
                    int(item.get("fromAccountId") or 0),
                    int(item.get("toAccountId") or 0),
                    int(item.get("amountCents") or 0),
                    _millis_to_date(item.get("occurredAt")),
                    item.get("note") or "",
                    _millis_to_dt(item.get("createdAt")) or _now_iso(),
                ),
            )

        for item in reports:
            finance_db.execute(
                """
                INSERT INTO monthly_reports (month, opening_cents, income_cents, expense_cents,
                                             closing_cents, category_json, account_json, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, '[]', ?)
                """,
                (
                    item.get("month") or "",
                    int(item.get("openingCents") or 0),
                    int(item.get("incomeCents") or 0),
                    int(item.get("expenseCents") or 0),
                    int(item.get("closingCents") or 0),
                    item.get("categoryJson") or "{}",
                    _millis_to_dt(item.get("createdAt")) or _now_iso(),
                ),
            )

    return {
        "tasks": len(tasks),
        "plans": len(plans),
        "courses": len(courses),
        "courseSessions": len(course_sessions),
        "accounts": len(accounts),
        "transactions": len(transactions),
        "transfers": len(transfers),
        "reports": len(reports),
    }


def import_from_file(planner_db, finance_db, path: Path) -> dict[str, int]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return import_payload(planner_db, finance_db, payload)
