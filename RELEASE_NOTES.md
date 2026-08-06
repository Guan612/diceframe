# DiceFrame v1.9.9

## 中文

这个版本带来地图、卡片、更新频道与插件稳定性改进：地图在几百个地点时自动铺开不再堆成一圈，支持缩放平移和回到当前场景；卡片渲染成为通用能力，外部聊天机器人也能发送卡片；设置页可切换预览版/正式版更新频道，并显示已安装插件的版本与更新提示；升级主程序后，已安装的插件不再丢失，会自动保留并继续使用；QQ/NapCat 插件内置，开箱即用。同时修复了更新提示跳转和旧版本升级迁移的问题。

### 新功能

- 插件跨版本保留：升级主程序后，从商店安装的插件不再丢失，会自动保留并继续使用；老用户升级时，之前安装的插件会自动迁移到数据目录，配置保持原样。
- QQ/NapCat 插件内置：安装主程序即可使用，开箱即用，无需从插件商店单独下载。
- 地图改进：地点自动力导向铺开，几百个地点不再挤成一圈；支持滚轮缩放、拖拽平移，一键回到当前场景。
- 卡片通用化：卡片渲染成为通用能力，外部聊天机器人也能收到并发送卡片。
- 更新频道：设置页可切换预览版/正式版，开启预览版会二次确认并提示不稳定。
- 已安装插件区显示当前版本号，商店有新版时提示更新。

### 修复

- 修复从商店安装的 QQ/NapCat 插件在剥离内置后的主程序上无法启动的问题。
- 修复从更新弹窗跳转到设置页后，新版本更新包不自动开始下载的问题。
- 修复从 1.9.5 及更早的旧布局便携版升级时，已安装的用户插件没有自动迁移到数据目录的问题。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v1.9.9-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v1.9.9-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

This release improves maps, cards, update channels, and plugin stability: maps with hundreds of locations now spread out automatically instead of piling into a circle, with zoom, pan, and a return-to-current-scene action; card rendering becomes a shared capability so external chat bots can send cards too; the settings page lets you switch between preview and stable update channels and shows installed plugin versions and update hints; plugins installed from the store are preserved across program upgrades; and the QQ/NapCat plugin is built in and works out of the box. It also fixes update-prompt navigation and plugin migration from older builds.

### New Features

- Plugin preservation across versions: after upgrading the main program, plugins installed from the store are no longer lost; they are preserved and keep working. For existing users, previously installed plugins migrate to the data directory automatically with settings intact.
- QQ/NapCat plugin built in: it works right after installing DiceFrame, no separate download from the plugin store needed.
- Map improvements: locations are laid out with force-directed spacing, so hundreds of locations no longer pile into one circle; scroll to zoom, drag to pan, and one click returns to the current scene.
- Card generalization: card rendering is now a shared capability, so external chat bots can receive and send cards.
- Update channel: the settings page lets you switch between preview and stable channels; enabling the preview channel asks for confirmation and warns that it may be unstable.
- Installed plugins now show their current version, and a hint appears when the store has a newer version.

### Fixes

- Fixed store-installed QQ/NapCat plugin failing to start on main programs that removed the built-in copy.
- Fixed the update package not starting to download automatically after navigating from the update dialog to the settings page.
- Fixed user-installed plugins not migrating to the data directory when upgrading from 1.9.5 and earlier portable builds with the legacy layout.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v1.9.9-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v1.9.9-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
