# 开源后的下一步（你需要自己做的）

本地仓库已经初始化并提交，但**没有远端**。下面是你需要做的。

## 1. 建 GitHub 仓库

1. 登录 GitHub，右上角 **New repository**；
2. 名称建议：`weekly-planner`；
3. **不要**勾选 “Add a README / .gitignore / license”（本地已有）；
4. 创建后拿到仓库地址，例如 `https://github.com/你的用户名/weekly-planner.git`。

## 2. 推送

如果电脑上有 Git：

```bash
cd weekly-planner-open
git remote add origin https://github.com/你的用户名/weekly-planner.git
git branch -M main
git push -u origin main
```

没有 Git 的话，装 [Git for Windows](https://git-scm.com/download/win)，或用 GitHub Desktop「Add local repository」选择这个文件夹再 Publish。

> 推送前再确认一次：`git status` 是干净的，`git ls-files` 里没有 `*.db`、`*.jks`、`keystore.properties`、真实课表。

## 3. 改掉占位邮箱

两个文件里的 `your-email@example.com`：

- `windows/src/author_note.py`
- `android/app/src/main/java/com/weeklyplanner/ui/screens/AuthorNoteSheet.kt`

改成你的反馈邮箱，或把「作者的话」里的邮箱按钮改成 GitHub Issues 链接。

## 4. 决定许可证

当前是 **MIT**。如果你希望衍生作品也必须开源，改成 GPL-3.0；改 `LICENSE` 并在 README 里同步即可。

## 5. 发布安装包（可选）

### Android

不要提交 keystore。可以在本地：

```bash
cd android
# 配置 keystore.properties（不要提交）
./gradlew assembleRelease
```

如果要用 GitHub Actions 自动签名，在仓库 **Settings → Secrets and variables → Actions** 添加：

- `ANDROID_KEYSTORE_BASE64`：`base64 release.jks`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

然后在 workflow 里解码 keystore 再 `assembleRelease`（当前仓库只放了测试 workflow，没有放签名 workflow，避免密钥误配）。

### Windows

当前仓库不带签名证书。自签名证书在别人电脑上仍显示「未知发布者」；想要可信签名，需要申请 **SignPath Foundation**（要求 OSI 许可证 + 公开仓库 + CI 签名）或 Azure Trusted Signing。

## 6. 加截图（可选）

只放自己重新截的图，确认没有：

- 真实姓名、学号；
- 真实金额、账户名；
- 本机路径、邮箱；
- 聊天窗口、通知里的个人信息。

放到 `docs/screenshots/`，在 README 里引用。

## 7. 国内分发

- 开源不等于免备案；国内应用商店/网站提供下载仍需 APP 备案；
- GitHub 访问不稳定可考虑 Gitee 镜像，但注意同步隐私清理。

## 8. 发布第一个 Release

```bash
git tag -a v1.0.14 -m "first open-source release"
git push origin v1.0.14
```

在 GitHub Releases 里上传自己构建的 Windows zip / Android APK，附 SHA256。

## 9. 维护

- 用 Issues 收集反馈；
- 不接受没有测试的 PR；
- 安全报告走私密渠道（见 `SECURITY.md`）；
- 每次改 JSON/数据库结构都更新 `docs/`。
