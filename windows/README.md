# 一周日程 · Windows 版

Windows 桌面端的周计划 + 记账工具，Python 3.12 + PySide6 + SQLite，所有数据保存在本机。

## 功能

- **周视图**：周一～周日 7 列 + 时间轴，课程背景、任务/计划/截止叠加；
- **任务**：标题、备注、分类、优先级、截止时间、完成状态，一个任务可挂多个计划时间；
- **提醒**：截止前一天 09:00、计划前 N 分钟、稍后提醒、错过补发，支持系统通知/应用内浮窗/托盘；
- **记账**：资金分区、收入/支出、六类支出（自定义分类版可改）、转账、月度总结与结余结转；
- **课表**：导入 `.xls/.xlsx/.csv/文字版 PDF`，支持从文本粘贴；无时间课表可自定义每节时间；
- **数据**：SQLite 备份/恢复、CSV 导入导出、与 Android 的 JSON 互通；
- **托盘/快捷键/开机启动**。

## 运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 测试

```bash
python -m unittest discover -s tests -t .
```

> 仓库里不放真实课表样例；依赖真实样例的测试会自动跳过。

## 打包

```bash
pip install pyinstaller
pyinstaller weekly_planner.spec --noconfirm
```

产物在 `dist/WeeklyPlanner/`；数据仍在 `%APPDATA%\WeeklyPlanner`，升级不会丢。

## 目录

```
src/         应用代码
tests/       单元测试
assets/      图标
main.py      入口
weekly_planner.spec  PyInstaller 配置
```

## 数据位置

- `%APPDATA%\WeeklyPlanner\planner.db`
- `%APPDATA%\WeeklyPlanner\finance.db`

明文 SQLite；备份文件请自己保管。

## 许可证

MIT；第三方依赖许可见仓库根目录 `NOTICE`。
