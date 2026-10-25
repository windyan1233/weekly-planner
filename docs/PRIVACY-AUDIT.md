# 开源前隐私清理记录

本仓库是从本地开发目录复制出来、清理后的版本。以下内容**没有**进入新仓库。

## 已移除

| 内容 | 位置（原工程） | 原因 |
| --- | --- | --- |
| 真实课表 `.xls` 样例 | `weekly_planner/tests/fixtures/student_schedule.xls`、`student_schedule_resaved.xls` | 含真实姓名、学号 |
| 真实课表 `.xls` 样例 | `android_planner/app/src/test/resources/student_schedule.xls` | 含真实姓名、学号 |
| 发布压缩包 / APK / 构建目录 | `发布/`、`dist/`、`app/build/`、`build/` | 体积大、含旧版本，且可能含本机路径 |
| 签名配置 / 密钥 | `keystore.properties`、`*.jks`、自签名证书 | 密钥不能公开 |
| 本机 SDK/IDE 配置 | `local.properties`、`.idea/`、`.vscode/` | 本机路径 |
| 截图与手册成品 | `tools/screenshots/`、`docs/*.docx`、`docs/*.pdf`、`发布/` | 截图可能含真实数据；成品可重建 |
| 构建/签名辅助脚本 | `tools/build_release.py`、`sign_exe.ps1`、`make_signing_cert.ps1`、`install_app.py` 等 | 含本机路径、证书口令流程，不适合直接公开 |

## 已脱敏

| 内容 | 处理 |
| --- | --- |
| 作者邮箱 | 替换为 `your-email@example.com`（Windows `src/author_note.py`、Android `AuthorNoteSheet.kt`），并加 TODO 注释 |
| 文档中的本机工具链路径 | 改为通用路径（如 `C:\android-toolchain`） |
| 文档中的 keystore 路径 | 改为 `release.jks`，并说明密码自己保管 |
| Windows README 里的截图/手册链接 | 已重写为简洁 README，不再引用未公开的截图和成品 |

## 仍然保留的公开信息

- 包名 `com.weeklyplanner`；
- 应用名「一周日程 / Weekly Planner」；
- 图标、界面文案；
- 作者自述（不含真实姓名、学校、学号、邮箱）；
- 示例课程名（如「高等数学」「体能训练」），均为通用名称。

## 你还需要自己做的

1. 建 GitHub 仓库并 `git push`（本仓库只做了本地 git 初始化，没有远端）；
2. 决定最终许可证（当前是 MIT，可改）；
3. 把 `your-email@example.com` 换成你的反馈邮箱，或改成 GitHub Issues 链接；
4. 如果要发布 Android 安装包：在 GitHub Secrets 配置 keystore（不要提交）；
5. 如果要发布 Windows 安装包：自签名证书对公众仍显示「未知发布者」，需要 SignPath/Azure Trusted Signing 才有可信签名；
6. 如果要放截图：只放自己重新截的、没有真实姓名/学号/金额/路径的图；
7. 国内上架仍需 APP 备案，开源不豁免。

## 检查命令（你可以自己再跑）

```bash
# 搜索可能残留的真实信息（按你自己的姓名/邮箱/路径替换关键词）
grep -RIn "你的姓名" .
grep -RIn "你的邮箱" .
grep -RIn "你的本机路径" .

# 密钥/数据库/构建产物
git status --ignored
```
