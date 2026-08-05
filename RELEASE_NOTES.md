# DiceFrame v1.9.5

## 中文

这个版本带来了语音朗读、插件更新检测与稳定性修复：GM 叙事和玩家行动可以点击喇叭朗读（可选自动朗读、可调速），插件商店能识别真正的"有新版本"；同时修复了 QQ/NapCat 插件的崩溃循环、Docker 升级丢插件等问题。

### 新功能

- 语音朗读：时间线里的 GM 叙事和玩家行动都可以点击喇叭朗读，支持自动朗读新叙事、调节语速（0.5–5.0），使用浏览器本地语音，无需联网。
- 插件商店检测更新：商店对比插件仓库的最新正式 Release 与本地已装版本，只有真有新版才显示"更新"按钮和"新版本"提示。
- 创建新冒险时可直接导入 DiceFrame 角色卡，与角色管理页一致。

### 修复

- 修复 QQ/NapCat 插件崩溃循环重启：残留锁文件把无关进程误判为存活导致无限重启，现在会校验进程身份，僵尸/无关进程残留锁会自动清理自愈。
- 修复插件崩溃重启不等待：反复起不来的插件现在会逐步退避重试，不再 3 秒高频冲击，稳定运行后自动恢复正常节奏。
- 修复 qq-napcat 在 Docker 下无限重启：父进程监控误判容器主进程为"已退出"导致插件反复重启，现在只做纯存活检测，NapCat 断连时静默重试连接，不再整个退出循环。
- 修复 Docker 升级后插件丢失：插件源码目录纳入持久卷挂载，容器重建后已安装插件不再消失。**已部署的 Docker/NAS 用户需要手动给 compose 加一行挂载 `- ./plugins:/app/plugins` 并重建容器，否则升级后插件源码仍会丢失。**
- 修复语音朗读读出样式代码：朗读前剥离 HTML 标签与实体，不再把 `<span>` 之类标签读出来。
- 未选择头像的角色不再自动分配头像，改为显示空白占位。

### 优化

- 插件更新改为手动：内容包/主题等声明型插件不再自动更新，商店提示新版后由你点"更新"安装，避免作者新代码未经确认就自动生效。
- GM 叙事字数约束强化：普通叙事 200-260 字、战斗/Boss 不超过 400 字，超长视为不合格；叙事压缩触发线提前，超长更早被收敛。
- 英文叙事压缩优化：英文按词数设定压缩目标（普通约 150 词、战斗约 200 词），不再被压缩到中文同等字符数的 1/3；叙事压缩目标改为按语言配置，为未来新增语言铺路。
- 朗读语速上限提升至 5.0。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v1.9.5-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v1.9.5-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

This release adds text-to-speech reading and plugin update detection with stability fixes: GM narration and player actions can be read aloud with a speaker button (optional auto-read, adjustable speed), and the plugin store now detects real "new versions". It also fixes the QQ/NapCat plugin crash loops, Docker upgrades dropping plugins, and more.

### New Features

- Text-to-speech: GM narration and player actions in the timeline can be read aloud with a speaker button; supports auto-reading new narration and adjustable speech rate (0.5–5.0), using the browser's local voices with no network needed.
- Plugin store update detection: the store compares each plugin's latest stable release against your installed version; the "Update" button and "New version" badge only appear when a newer version really exists.
- DiceFrame character cards can now be imported directly while creating a new game, matching the character management page.

### Fixes

- Fixed QQ/NapCat plugin crash-restart loop: a stale lock file could mistake an unrelated process as alive and cause endless restarts; process identity is now verified, and locks from zombie/unrelated processes are cleaned up automatically.
- Fixed plugin crash restarts not backing off: plugins that repeatedly fail to start now retry with growing delays instead of hammering every 3 seconds, and recover once stable.
- Fixed qq-napcat infinite restarts under Docker: parent-process monitoring misjudged the container's main process as "exited", causing the plugin to restart in a loop; it now uses pure liveness detection and silently retries the NapCat connection instead of exiting the whole loop.
- Fixed plugins disappearing after Docker upgrades: the plugin source directory is now on a persistent volume, so installed plugins survive container rebuilds. **Existing Docker/NAS users need to add the mount `- ./plugins:/app/plugins` to their compose file and recreate the container — otherwise plugin sources will still be lost on upgrade.**
- Fixed the narrator reading out markup: HTML tags and entities are stripped before reading, so tags like `<span>` are no longer spoken.
- Characters without a chosen portrait now show an empty placeholder instead of an auto-assigned one.

### Improvements

- Plugin updates are now manual: declarative plugins (content packs/themes) no longer auto-update; the store notifies you of a new version and it installs only after you click "Update", so newly published author code never applies without your confirmation.
- Stricter GM narration length: ordinary narration must stay within 200-260 characters and combat/boss scenes within 400; narration compression triggers earlier for oversized text.
- English narration compression tuned: English narration is compressed toward word-count targets (about 150 words normally, 200 in combat) instead of being shrunk to a third of the Chinese character target; compression limits are now configured per language, paving the way for future languages.
- Speech rate upper limit raised to 5.0.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v1.9.5-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v1.9.5-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
