# DiceFrame v2.0.0-beta.4

## 中文

这是 2.0.0 的第二个预览版，自 v2.0.0-beta.3 起修复了支付与幸运选择的体验问题，并把插件商店拆分为**插件商店 / 内容商店**两个入口。预览版用户可以更新体验；正式版频道不受影响。

### 修复与体验

- **支付流程**：创建角色余额不足时，不再反复弹出支付窗口——自动取消未完成的支付订单，避免弹窗循环打扰。
- **幸运选择**：'保留失败'按钮改为与'消耗幸运点'一致的红色 pill 样式，两个选项一眼可辨。

### 插件商店

- **商店拆分**：插件页新增"插件商店 / 内容商店"两个选项卡——内容商店专注展示内容包类资源，插件商店聚焦机器人接入、工具、主题等插件，查找更直接。
- **地图包调整**：地图包（map-pack）暂不支持在线安装，相关条目不再出现在商店可安装列表中，避免误导。
- **目录刷新**：商店目录缓存从 30 天缩短为 1 天，上架与更新能更快看到；目录过期时来源旁会出现刷新按钮。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v2.0.0-beta.4-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v2.0.0-beta.4-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

This is the second 2.0.0 preview, fixing payment and luck-selection experience issues and splitting the plugin store into **Plugin Store / Content Store** tabs. Preview-channel users can update and try it; the stable channel is unaffected.

### Fixes & Experience

- **Payment flow**: when balance is insufficient while creating a character, the pending payment order is now cancelled automatically instead of repeatedly popping up the payment dialog.
- **Luck selection**: the "Keep failure" button now uses the same red pill style as "Spend luck point", so the two options are easy to tell apart.

### Plugin Store

- **Store split**: the Plugins page now has "Plugin Store / Content Store" tabs — Content Store focuses on content-pack resources, while Plugin Store focuses on bot adapters, tools, themes and other plugins, making discovery more direct.
- **Map pack**: map-pack is reserved for a future map editor and no longer appears as installable in the store.
- **Catalog refresh**: store catalog cache shortened from 30 days to 1 day so listings and updates appear faster; a refresh button appears next to the source when the catalog is stale.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v2.0.0-beta.4-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.0.0-beta.4-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
