# DiceFrame v2.1.1

## 中文

DiceFrame 2.1.1 是一次补丁更新，主要修复 Cloudflare 隧道状态与插件架构兼容问题，并优化游玩页技能详情和插件页展示。

### 修复

- **Cloudflare 隧道状态卡片**：只有隧道真正获得公网地址时才显示“运行中”；进入页面时正确加载访问密码；启停按钮保持可点，密码错误时会给出明确提示。
- **插件架构兼容**：插件宿主会向插件进程传递处理器架构信息，修复部分环境（如 Linux 云隧道使用的 cloudflared）无法识别正确架构的问题。
- **启动器架构**：DiceFrame.exe 启动器改为原生 x64 编译。

### 改进

- **技能详情**：游玩页角色技能支持鼠标悬浮查看摘要，并可打开“查看全部详情”弹窗。
- **插件页排版**：已安装插件的版本标签间距微调，信息更易读。
- **发布流程**：构建产物先校验再挂载到 Release，避免出现空壳版本。

## English

DiceFrame 2.1.1 is a patch release that fixes Cloudflare tunnel status and plugin architecture compatibility, and polishes skill details and the plugin page.

### Fixes

- **Cloudflare tunnel card**: shows "running" only when the tunnel actually has a public URL; loads the access password correctly when the page opens; keeps enable/disable clickable and surfaces password errors clearly.
- **Plugin architecture compatibility**: the plugin host now passes processor-architecture environment variables to plugin processes, fixing cloudflared and similar plugins on environments (such as Linux) that could not detect the right architecture.
- **Launcher architecture**: DiceFrame.exe is now compiled as a native x64 launcher.

### Improvements

- **Skill details**: hover over a character skill in the play view to preview details, or open the full "View all details" dialog.
- **Plugin page layout**: slightly more spacing for version tags on installed plugins.
- **Release pipeline**: build artifacts are verified before being attached to a Release, preventing empty releases.
