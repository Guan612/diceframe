# DiceFrame v2.6.1-beta.1

> 预发布版本：修复 Bot 图片卡片中文显示为 `□□□□`，并为 Windows 便携版加入崩溃取证（自动 MiniDump + `last-crash.json`），让原生闪退不再没有线索。

## 中文

### 修复内容

- **Bot 图片卡片中文方框**：卡片渲染此前会在找不到系统字体时静默回退 Pillow 默认字体，而它不含中文字形——英文、数字正常，中文全部变成 `□□□□`。现在字体解析必须拿到**真正含 CJK 字形**的字体（比较中文与私用区码点的位图，识别只画方框的字体），候选路径覆盖 Windows / Debian / Alpine / macOS 常见中文与 Noto CJK 字体，并在显式路径全部落空时按名字扫描标准字体目录兜底；确实找不到字体时渲染明确失败，由渠道既有降级路径改发纯文本，**不再生成满屏方框的图片**。CI 后端任务会安装 `fonts-noto-cjk` 覆盖真实渲染路径，Docker 构建期也会断言字体确实装在被查找的路径上。

### 新增内容

- **Windows 便携版崩溃取证**：后端 `python.exe` 发生原生崩溃（例如 `0xC0000005`）时，便携版会自动保留证据：
  - 在 DiceFrame 运行期间临时启用 Windows Error Reporting LocalDumps（`HKCU`，无需管理员），崩溃时由系统写出 MiniDump 到 `logs/crash-dumps`（MiniDump，最多保留最近 3 个）；
  - 异常退出时写入 `logs/last-crash.json`：退出代码（`0xC0000005` 这种可读格式）、粗分类（access_violation / stack_overflow / heap_corruption 等）、启动与崩溃时间、运行时长、对应 dump 路径；
  - 控制台不再瞬间消失，而是显示错误代码、类型与 `logs` 目录，提示把 `logs` 文件夹打包反馈。
  - 隐私与安全边界：临时 WER 配置只在 DiceFrame 生命周期内存在，正常关闭、崩溃、更新重启、启动失败都会恢复用户原有设置；dump 只认本次后端进程（按 PID 匹配），**不自动上传**，诊断记录不含 API Key、prompt、聊天正文或角色信息；不需要时可直接删除 `logs/crash-dumps`。
  - 更新流程主动停止旧进程不会误报为崩溃；崩溃诊断本身启用失败也不会阻止 DiceFrame 启动。

### 升级说明

- 本版无存档 schema 变更，无需迁移；旧存档、自定义规则与插件继续可用。
- Windows 便携版会在运行期间临时写入并恢复 `HKCU\Software\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe`；如系统 Windows Error Reporting 服务被禁用，则不会产生 dump，但异常退出记录仍会写入。
- 升级重要对局前建议备份完整的 `data/` 目录。

### 下载与校验

- **普通 Windows 用户**：`DiceFrame-v2.6.1-beta.1-windows-portable.zip`
- **源码运行用户**：`DiceFrame-v2.6.1-beta.1-windows.zip`
- **托管 Docker 更新**：`DiceFrame-v2.6.1-beta.1-docker-update-linux-amd64.zip`
- 下载后请使用 Release 中的 `SHA256SUMS` 校验文件。

## English

### Fixes

- **Chinese glyphs rendering as boxes on bot image cards**: card rendering silently fell back to Pillow's default font when no system font was found, and that font has no CJK glyphs — Latin text looked fine while every Chinese character became `□□□□`. Font resolution now requires a font that really draws CJK (Chinese text is compared against private-use codepoints to detect fonts that only draw boxes), covers the common Windows / Debian / Alpine / macOS CJK and Noto CJK paths, and falls back to a name-filtered scan of standard font directories when every explicit path is missing. When no such font exists, rendering fails explicitly and the channel's existing degradation path sends plain text instead of shipping a box-filled image. CI installs `fonts-noto-cjk` so the real rendering path is covered, and the Docker build asserts the font really lands where the renderer looks.

### New

- **Windows Portable crash forensics**: when the bundled `python.exe` dies from a native crash (for example `0xC0000005`), the portable build now preserves evidence automatically:
  - Windows Error Reporting LocalDumps is enabled temporarily for the DiceFrame lifetime (`HKCU`, no admin rights) so Windows writes a MiniDump into `logs/crash-dumps` (MiniDump, newest 3 kept);
  - abnormal exits write `logs/last-crash.json` with a readable exit code (`0xC0000005`), a coarse classification (access_violation / stack_overflow / heap_corruption, …), start/crash times, uptime and the matching dump path;
  - the console no longer vanishes instantly: it shows the exit code, the classification and the `logs` folder, and asks the user to zip `logs` when reporting.
  - Privacy and safety: the temporary WER configuration only exists for the DiceFrame lifetime and the user's original settings are restored on normal exit, crash, update restart and startup failure; dumps are matched to this backend process by PID and are **never uploaded**; the record contains no API keys, prompts, chat text or character data; `logs/crash-dumps` can simply be deleted when not needed.
  - Managed-update stops are not misreported as crashes, and a failure to enable crash diagnostics never blocks DiceFrame from starting.

### Upgrade notes

- No save schema changes and no migration; existing saves, custom rules and plugins keep working.
- The Windows portable build temporarily writes and then restores `HKCU\Software\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe`; if the Windows Error Reporting service is disabled, no dump is produced, but the abnormal-exit record is still written.
- Back up the complete `data/` directory before upgrading important campaigns.

### Downloads and verification

- **Regular Windows users**: `DiceFrame-v2.6.1-beta.1-windows-portable.zip`
- **Source users**: `DiceFrame-v2.6.1-beta.1-windows.zip`
- **Managed Docker update**: `DiceFrame-v2.6.1-beta.1-docker-update-linux-amd64.zip`
- Verify downloads with the `SHA256SUMS` file attached to the Release.
