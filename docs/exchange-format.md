# JSON 互通格式（摘要）

完整说明见 [一周日程-双端功能与互通说明.md](一周日程-双端功能与互通说明.md) 第 5 节。

- 格式名：`weekly-planner-exchange`
- 版本：`1`
- 单位：金额为**分**，时间为 **epoch 毫秒**，星期 `0 = 周一`
- 根字段：

```json
{
  "format": "weekly-planner-exchange",
  "version": 1,
  "source": "windows",
  "app": "weekly-planner",
  "exportedAt": 1760000000000,
  "tasks": [],
  "plans": [],
  "accounts": [],
  "transactions": [],
  "transfers": [],
  "reports": [],
  "courses": [],
  "courseSessions": []
}
```

## 主要字段

| 数组 | 字段 |
| --- | --- |
| `tasks` | id, title, note, kind, priority, dueAt, done, createdAt, updatedAt |
| `plans` | id, taskId, planAt |
| `accounts` | id, name, openingCents, sortOrder, archived, createdAt |
| `transactions` | id, type(expense/income), amountCents, categoryKey, accountId, title, note, occurredAt, createdAt |
| `transfers` | id, fromAccountId, toAccountId, amountCents, note, occurredAt, createdAt |
| `reports` | month, incomeCents, expenseCents, openingCents, closingCents, categoryJson, createdAt |
| `courses` | id, name, teacher, location, descriptor, color, createdAt |
| `courseSessions` | id, courseId, day(yyyy-MM-dd), startMinutes, endMinutes |

## 注意

- 导入是**整体覆盖**，不是合并；导入前先导出备份。
- 自定义支出分类不写入 JSON，只保留 `categoryKey`；两端要有同名 key 才能显示名称。
- `plans.taskId`、`courseSessions.courseId` 必须能对应到同一文件里的 `tasks`/`courses`。
