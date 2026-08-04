# DiceFrame v1.9.2

## 中文

这个版本带来了语音朗读与更可靠的插件更新：GM 叙事和玩家行动可以点一下喇叭朗读（可选自动朗读、可调速），插件商店现在能识别真正的"有新版本"，只有真的有新版才显示更新按钮。同时修复了 QQ/NapCat 插件的崩溃循环重启，以及未选头像时自动分配造成的不一致问题。

### 新功能

- 语音朗读：时间线里的 GM 叙事和玩家行动都可以点击喇叭朗读，支持自动朗读新叙事、调节语速，使用浏览器本地语音，无需联网。
- 插件商店检测更新：商店现在对比插件仓库的最新正式 Release 与本地已装版本，只有真有新版才显示"更新"按钮和"新版本"提示，不再一律显示更新。
- 创建新冒险时可直接导入 DiceFrame 角色卡，与角色管理页一致。

### 修复

- 修复 QQ/NapCat 插件崩溃循环重启：残留锁文件把无关进程误判为存活导致无限重启，现在会校验进程身份，僵尸/无关进程残留锁会自动清理自愈。
- 修复插件崩溃重启不等待：反复起不来的插件现在会逐步退避重试，不再 3 秒高频冲击，稳定运行后自动恢复正常节奏。
- 未选择头像的角色不再自动分配头像，改为显示空白占位，避免"没选却有个默认头像"的困惑。

### 优化

- 插件自动更新时机调整：启动不再检查更新，改为打开插件商店时后台检查，减少启动开销。
- 主程序更新页按钮文案统一为"下载更新"。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v1.9.2-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v1.9.2-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

This release adds text-to-speech reading and more reliable plugin updates: GM narration and player actions can be read aloud with a speaker button (optional auto-read, adjustable speed), and the plugin store now detects real "new versions" — the update button only appears when a newer version actually exists. It also fixes the QQ/NapCat plugin's crash-restart loop and stops auto-assigning portraits when none was chosen.

### New Features

- Text-to-speech: GM narration and player actions in the timeline can be read aloud with a speaker button; supports auto-reading new narration and adjustable speech rate, using the browser's local voices with no network needed.
- Plugin store update detection: the store now compares each plugin's latest stable release against your installed version; the "Update" button and "New version" badge only appear when a newer version really exists.
- DiceFrame character cards can now be imported directly while creating a new game, matching the character management page.

### Fixes

- Fixed QQ/NapCat plugin crash-restart loop: a stale lock file could mistake an unrelated process as alive and cause endless restarts; process identity is now verified, and locks from zombie/unrelated processes are cleaned up automatically.
- Fixed plugin crash restarts not backing off: plugins that repeatedly fail to start now retry with growing delays instead of hammering every 3 seconds, and recover to the normal rhythm once stable.
- Characters without a chosen portrait now show an empty placeholder instead of an auto-assigned one, removing the "didn't pick one but got a default" confusion.

### Improvements

- Plugin auto-update timing: startup no longer checks for updates; the store checks in the background when opened, reducing startup overhead.
- The update page button label is now consistently "Download update".

### Download Guide

- **Regular Windows users**: download `DiceFrame-v1.9.2-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v1.9.2-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
