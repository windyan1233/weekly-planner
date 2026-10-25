# 一周日程 · Weekly Planner

一个**纯本地**的周计划 + 记账工具，包含 Windows 和 Android 两端。

- 日程：周视图、多计划时间、截止时间、分类/优先级、课程表；
- 提醒：截止前一天、计划前 N 分钟、稍后提醒、错过补发；
- 记账：资金分区、收入/支出、六类（可自定义）分类、转账、月度报表与结转；
- 互通：两端通过同一套 JSON 格式手动导入/导出；
- 隐私：不联网、不登录、不收集数据；Android 无 `INTERNET` 权限。

> 当前仓库是整理后的开源版本，功能说明见 [docs/一周日程-双端功能与互通说明.md](docs/一周日程-双端功能与互通说明.md)。

## 仓库结构

```
windows/   Windows 版（Python 3.12 + PySide6 + SQLite）
android/   Android 版（Kotlin + Jetpack Compose + Room）
docs/      功能说明、JSON 格式
```

## 功能概览

| 功能 | Windows | Android |
| --- | --- | --- |
| 周视图 | ✅ | ✅ 默认 |
| 列表视图 | — | ✅ |
| 多计划时间 | ✅ | ✅ |
| 截止/计划提醒 | ✅ | ✅ |
| 应用内浮窗 | ✅ 可关 | ❌ 仅系统通知 |
| 记账/转账/月报结转 | ✅ | ✅ |
| 自定义支出分类 | 自定义分类版 | ✅ 内置 |
| 课表 `.xls/.xlsx/.csv` | ✅ | ✅ |
| 课表文字版 `.pdf` | ✅ | ❌ |
| 文字版 PDF 扫描件 | ❌ 无 OCR | ❌ 无 OCR |
| JSON 互通 | ✅ | ✅ |
| SQLite 备份 | ✅ | ❌（用 JSON） |

详细差异与限制见文档。

## 构建

### Windows

要求：Python 3.12+、Windows 10/11。

```bash
cd windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m unittest discover -s tests -t .
python main.py
```

打包（可选）：

```bash
pip install pyinstaller
pyinstaller weekly_planner.spec --noconfirm
```

产物在 `windows/dist/WeeklyPlanner/`。数据默认在 `%APPDATA%\WeeklyPlanner`。

### Android

要求：JDK 17、Android SDK 34、Gradle 8.7（仓库带 wrapper 时直接用 `./gradlew`）。

```bash
cd android
./gradlew test
./gradlew assembleDebug
```

Release 签名需要自己在 `android/keystore.properties` 里配置（不要提交）：

```properties
storeFile=../release.jks
storePassword=***
keyAlias=***
keyPassword=***
```

然后：

```bash
./gradlew assembleRelease
```

## 数据与隐私

- Windows 数据：`%APPDATA%\WeeklyPlanner\planner.db`、`finance.db`；
- Android 数据：应用私有目录的 `planner.db`；
- 两端都不联网，Android 没有 `INTERNET` 权限；
- 数据是明文 SQLite，备份文件请自己保管；
- Android `allowBackup=true` 可能被系统云备份，介意可在系统设置关闭。

## JSON 互通

格式名：`weekly-planner-exchange`，版本 `1`，金额单位为分，时间为 epoch 毫秒。字段与导入覆盖规则见 [docs/一周日程-双端功能与互通说明.md](docs/一周日程-双端功能与互通说明.md) 第 5 节。

## 文档

- [双端功能与互通说明](docs/一周日程-双端功能与互通说明.md)
- [JSON 格式摘要](docs/exchange-format.md)
- [隐私清理记录](docs/PRIVACY-AUDIT.md)

## 关于作者

我是一名非计算机专业的大一学生，这个项目是我在 AI 辅助下完成的：代码可能不够成熟，但功能都在真实使用。

欢迎通过 Issue 提建议；如果这个项目对你有帮助，点个 Star 就是最大的鼓励。

> 应用内「我的 → 作者的话」有更完整的说明。

## 许可证

MIT，见 [LICENSE](LICENSE)。第三方依赖许可见 [NOTICE](NOTICE)。

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。提交前请确认没有把真实课表、数据库、密钥或个人路径带进仓库。
