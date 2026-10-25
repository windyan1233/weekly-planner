# 一周日程 · Android 版

日程 + 记账 + 月报 + 资金管理，Kotlin + Jetpack Compose + Room，数据只在本机，无 `INTERNET` 权限。

## 功能

- **日程**：默认周视图（7 列 × 07:00–23:00），可切换列表；课程、计划、截止重叠显示；
- **任务**：标题、备注、分类、优先级、截止、多个计划时间、完成状态；
- **提醒**：截止前一天、计划前 N 分钟、开机/时区变化重排、WorkManager 兜底；
- **记账**：资金分区、收入/支出、六类支出（可自定义）、转账、月度报表与结转；
- **课表**：导入 `.xls/.xlsx/.csv`，多工作表优先「课程明细」，无时间课表可自定义每节时间；
- **数据**：JSON 导出/导入，支持从其他应用「用一周日程打开」；
- **我的**：资金分区、支出分类、权限、课表、作者的话。

## 构建

要求：JDK 17、Android SDK 34、Gradle 8.7。

```bash
./gradlew test
./gradlew assembleDebug
```

Release 签名在 `keystore.properties` 配置（不要提交）：

```properties
storeFile=../release.jks
storePassword=***
keyAlias=***
keyPassword=***
```

```bash
./gradlew assembleRelease
```

## 数据

- Room 数据库：应用私有目录 `databases/planner.db`；
- 无 `INTERNET` 权限；
- `allowBackup=true` 可能被系统云备份，介意可在系统设置关闭；
- 备份/迁移走「我的 → 数据 → 导出/导入 JSON」。

## 测试

```bash
./gradlew test
```

仓库不包含真实课表；测试使用自己编的示例数据。

## 许可证

MIT；第三方依赖许可见仓库根目录 `NOTICE`。
