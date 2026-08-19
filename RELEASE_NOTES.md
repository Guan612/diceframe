# DiceFrame v2.2.1

## 中文

DiceFrame 2.2.1 为规则作者补充资源结算能力，修复思考模式模型的检定规划问题，并优化 DF 助手。

### 新增

- **规则资源标签与阈值触发器**：GM 可用 `STAT:玩家ID:资源key:变化量` 标签在结算时直接增减规则特殊属性（KPI、谜团进度、倒计时等），服务端自动钳制上下限；`special_stats` 可声明阈值触发器（at/direction/notify），资源到达阈值时向 GM 注入系统提示推进剧情。GM 数值指令别名同步支持从规则资源动态推导。

### 修复

- **思考模式模型检定规划失败**：使用 DeepSeek 等带思考模式的模型时，AI 检定规划偶发失败并回退到简化检定；现在自动切换兼容调用方式并在输出截断时自动放大重试。
- **规则特殊属性初始值**：freeform_wuxia 内力改为显式满值起步，避免依赖引擎默认值（规则作者侧修复）。

### 改进

- **DF 助手优化**：接入完整官方文档（用户手册/部署/插件开发等），回答更准，文档更新自动同步。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v2.2.1-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v2.2.1-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

DiceFrame 2.2.1 adds resource-adjudication tools for rule authors, fixes AI check planning with reasoning models, and improves the DF Assistant.

### New

- **Rule resource tags and threshold triggers**: GMs can use `STAT:player_id:resource_key:delta` tags to adjust rule-defined special stats (KPI, puzzle progress, countdowns, etc.) directly during resolution, with server-side clamping to min/max; `special_stats` may declare threshold triggers (at/direction/notify) that inject a system prompt to the GM when a resource crosses a threshold. GM numeric command aliases are now derived from rule resources dynamically.

### Fixes

- **Check planning failed with reasoning models**: when using reasoning models such as DeepSeek's thinking mode, AI check planning could intermittently fail and fall back to simplified checks; the client now switches to a compatible calling convention automatically and retries with a larger token budget on truncation.
- **Rule special-stat initial values**: freeform_wuxia's qi now starts explicitly at full value instead of relying on engine defaults (rule-author-side fix).

### Improvements

- **DF Assistant**: now grounded in the full official docs (user guide, deployment, plugin development, etc.) for more accurate answers, with doc updates synced automatically.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v2.2.1-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.2.1-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
