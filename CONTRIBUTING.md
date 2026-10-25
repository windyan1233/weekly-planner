# 贡献指南

感谢愿意帮忙改进「一周日程」。

## 开发环境

### Windows

- Python 3.12+
- Windows 10/11

```bash
cd windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m unittest discover -s tests -t .
```

### Android

- JDK 17
- Android SDK 34
- Gradle 8.7（有 wrapper 时用 `./gradlew`）

```bash
cd android
./gradlew test
```

## 提交前检查

1. 测试通过；
2. **不要提交**真实课表、数据库、备份、`keystore.properties`、`*.jks`、`local.properties`；
3. 新增测试不要依赖真实个人信息，用自己编的「张三 / 20260001」之类假数据；
4. UI 改动请附截图，但截图里不能出现真实姓名、学号、金额、路径。

## 代码风格

- Python：4 空格缩进，类型标注优先，避免裸 `except`；
- Kotlin：官方风格，Compose 组件保持小函数；
- 提交信息用中文或英文一句话说明「改了什么」，不要写「update」。

## Pull Request

- 一个 PR 只做一件事；
- 说明「为什么改」和「怎么验证」；
- 如果改了 JSON 格式或数据库结构，必须同时更新文档并说明兼容性。
