# DiceFrame v2.0.0-beta.2

## 中文

这是 2.0.0 的首个预览版，自 v1.9.12-beta.2 起累计 41 个提交、367 个文件变更，涵盖**多语言基础设施、代码重构、安全加固、AI 助手、插件生态与大量游玩体验修复**。预览版用户可以更新体验；正式版频道不受影响。

### 新功能

- **多语言（国际化）基础设施**：后端本地化从中文/英文二元改为按语言查表分发（`localized_text`），为更多语言打底。本版以**日语**为第三语言样板完成全链路（规则模板、检定词表、GM 提示、前端界面），可在登录页或设置页切换语言。后续新功能/文案不强制同步日文翻译，缺失时自动回退中文。
- **AI 助手本地知识包**：内置预建知识包，助手回答更贴近项目实际情况；助手来源展示简化。
- **插件商店生态**：工具型插件可渲染专用操作卡片（如外网接入卡）；商店条目显示所需 DiceFrame 最低版本并提示升级；支持更大插件包为二进制进程插件铺路。
- **公告系统**：新增公告拉取与展示（官方内容经 Hub 网络获取）。

### 架构与工程

- **代码重构**：`GameInstance` 幸运三方法与存档逻辑分别拆到 `luck_resolver` / `persistence` 独立模块；前端样式拆分 22 个模块、插件设置页拆分 8 个子组件，职责更清晰。
- **安全与健壮性**：规则表达式求值加嵌套深度上限；叙事压缩失败降级硬截断；连续标签解析失败给玩家可见提示；memory 召回改粗筛防漏旧记忆；generation 禁用词双语化；`_safe_eval` 防护。
- **CI**：后端流水线新增 ruff lint 与 mypy 类型检查。
- **骰子判定**：SAN 检定大成功不再按失败结算；CoC 自定义技能基础值兜底防超模建卡；`check_planner` 提示词加强物理破坏类行动应检定；GM 指令目标解析真名优先（修复"复活冒险者"被误拒）。
- **幸运机制**：多人幸运改判改为每玩家独立超时（默认 60 秒可配），不再一人挂机全桌等。

### 游玩体验

- **世界书/游戏日志页**：未进入存档或未选择世界时显示整洁单列空态，不再错乱。
- **剧情提示**：推进回合后不再用顶部气泡重复弹出剧情全文。
- **难度机制**：硬核难度禁止复活（角色可永久死亡），落实难度差异。
- **Hub 访问**：请求超时从 3 秒/6 秒放宽到 30 秒，减少 Hub 站缓慢时误触发熔断、插件详情打不开。
- **默认模型**：默认模型调整为 `deepseek-v4-flash`。
- **设置页"支持项目"与 GitHub Star**：并排一行展示、文字左对齐。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v2.0.0-beta.2-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v2.0.0-beta.2-windows.zip`。
- `.sha256` 是更新校验文件，普通用户不需要手动下载。

## English

This is the first 2.0.0 preview, accumulating 41 commits and 367 file changes since v1.9.12-beta.2: the **i18n foundation, refactors, hardening, AI assistant, plugin ecosystem**, and many play-experience fixes. Preview-channel users can update and try it; the stable channel is unaffected.

### New Features

- **i18n foundation**: backend localization moved from a Chinese/English binary switch to per-language lookup (`localized_text`). **Japanese** ships as the sample third language across rule templates, intent tables, GM prompts, and the UI; switch language from Login or Settings. Future features/copy do not force synchronized Japanese translation, falling back to Chinese when absent.
- **AI assistant knowledge pack**: bundled local knowledge base for more accurate assistant answers; simplified source display.
- **Plugin ecosystem**: tool plugins render dedicated operation cards (e.g. external-access card); store entries show the minimum DiceFrame version and prompt upgrades; larger packages supported for binary process plugins.
- **Announcements**: official content fetched from the Hub over the network and shown to users.

### Architecture & Engineering

- **Refactors**: `GameInstance` luck methods and save logic split into `luck_resolver` / `persistence`; frontend styles split into 22 modules; plugin settings page split into 8 sub-components.
- **Hardening**: rule-expression evaluation gains a nesting-depth cap; narration compression falls back to hard truncation on failure; consecutive tag-parse failures show a player-visible notice; memory recall uses coarse filtering to avoid missing older relevant entries; generation banned-word checks are bilingual; `_safe_eval` guarded.
- **CI**: added ruff lint and mypy type-checking to the backend pipeline.
- **Dice & rules**: SAN critical success no longer resolves as failure; CoC custom-skill base fallback prevents overpowered sheets; `check_planner` prompt strengthened for physical actions (prying/breaking) to warrant checks; GM command target resolution prioritizes exact names (fixes wrongly-rejected "revive Adventurer").
- **Luck**: multiplayer luck decisions get a per-player timeout (default 60s, configurable) instead of blocking the whole table for one player.

### Play Experience

- **Lorebook / game log pages**: clean single-column empty states when no save/world is selected.
- **Narration toast**: advancing a round no longer re-pops the full narration in a top toast.
- **Difficulty**: hardcore difficulty disables revival (characters can permanently die).
- **Hub access**: timeouts widened from 3s/6s to 30s, reducing false circuit-breaking when the Hub is slow.
- **Default model**: switched to `deepseek-v4-flash`.
- **Support Project + GitHub Star buttons**: side by side in Settings, text left-aligned.

### Download Guide

- **Regular Windows users**: download `DiceFrame-v2.0.0-beta.2-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.0.0-beta.2-windows.zip`.
- `.sha256` files are update checksums; regular users do not need to download them manually.
