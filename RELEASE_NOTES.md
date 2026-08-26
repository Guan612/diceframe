# DiceFrame v2.3.2

## 中文

DiceFrame 2.3.2 是 Content V2 架构、规则与世界书多语言本地化、旧数据迁移链路的正式补丁版。重要战役升级前仍建议备份现有 `data/`。

### 内容与本地化

- **Content V2 正式进入运行时**：规则、世界、职业、物品、法术和 NPC 使用稳定的 canonical ID；中文、英文和日文只覆盖显示文本，切换语言不会改变存档、规则或世界书 identity。
- **规则与世界的 typed locale**：内置规则和世界支持按游戏语言物化的名称、说明、场景与世界书文本；缺失语言会按既定 fallback 回退，不会静默改写 mechanics。
- **运行时模板同步修复**：启动时会将内置的嵌套 locale JSON 同步到 `data/templates`，确保真实部署与开发加载器一致。
- **世界书角色本地化**：角色面板和世界书 NPC 的头像物化会使用当前对局语言的只读本地化视图，译文不会写回共享世界书数据库。
- **模型配置兼容修复**：创建游戏页同时识别旧版内联模型配置和新版 AI 服务商模型配置，连接测试通过后可以正常创建游戏。

### 规则、迁移与客户端

- **D&D 5e Lite Content V2**：D&D 轻规则的职业、装备、伤害和角色创建数据迁入 canonical 内容模型，同时保持 generic d20 与 D&D 专属逻辑的边界。
- **旧数据兼容与迁移**：旧规则、世界书、角色和存档会先经过明确的 compatibility/migration 边界再进入当前模型，减少升级后 legacy 字段与索引不一致的问题。
- **战斗与长战役可靠性**：补强检定权威、死亡豁免、状态更新和长战役重算的覆盖，避免重试时重复结算。
- **实验性移动端客户端**：仓库新增 Expo 移动端客户端与共享 API/流式交互覆盖；本次 Release 附件暂不提供移动端安装包。

### 使用提示

- 建议在现有战役和自定义模板上先做副本验证；遇到问题请保留日志和最小复现。
- 可下载附件为 Windows 源码包和 Windows 便携包；移动端需要从仓库源码自行运行。
- 玩家直连仍为实验性功能：对称 NAT 或严格防火墙可能阻止连接，房主必须保持 DiceFrame 和房间在线。

### 下载指南

- **普通 Windows 用户**：下载 `DiceFrame-v2.3.2-windows-portable.zip`。
- **源码运行用户**：下载 `DiceFrame-v2.3.2-windows.zip`。
- `.sha256` 是更新校验文件；升级前建议保留旧版本或数据备份，便于回退。

## English

DiceFrame 2.3.2 is the stable patch release for the Content V2 runtime architecture, localized rule and lorebook content, and the legacy-data migration path. Back up your existing `data/` before using it for an important campaign.

### Content and localization

- **Content V2 is active at runtime**: rules, worlds, classes, items, spells, and NPCs use stable canonical IDs. Chinese, English, and Japanese overlays change display text only, never save, rule, or lorebook identity.
- **Typed locales for rules and worlds**: bundled rules and worlds materialize names, descriptions, scenes, and lorebook text for the game language. Missing locales use the documented fallback path without silently changing mechanics.
- **Runtime template synchronization**: startup now copies nested bundled locale JSON into `data/templates`, aligning a deployed server with the development loader.
- **Localized lorebook characters**: the character panel and lorebook-NPC portrait materialization use a read-only view for the active game language; translations are never written back into the shared lorebook database.
- **Model configuration compatibility**: the create screen now recognizes both legacy inline model settings and the newer AI provider model library, so a successful connection test is enough to create a game.

### Rules, migration, and clients

- **D&D 5e Lite Content V2**: D&D Lite classes, equipment, damage, and character-creation data now use the canonical content model while keeping generic d20 behavior separate from D&D-specific logic.
- **Legacy compatibility and migration**: older rules, lorebooks, characters, and saves cross explicit compatibility and migration boundaries before entering the current model, reducing inconsistent legacy fields and indexes after upgrade.
- **Reliable combat and long campaigns**: stronger coverage for authoritative checks, death saves, state updates, and long-campaign recomputation helps retries avoid duplicate resolution.
- **Experimental mobile client**: the repository now includes an Expo mobile client with shared API and streaming coverage. This release does not attach mobile installation packages.

### Usage notes

- Test existing campaigns and custom templates on a copy first; retain logs and a minimal reproduction if anything fails.
- Downloadable assets are Windows source and Windows portable packages; the mobile client must currently be run from the repository source.
- Player direct connect remains experimental: symmetric NAT or strict firewalls may prevent connections, and the host must keep DiceFrame and the room online.

### Download guide

- **Regular Windows users**: download `DiceFrame-v2.3.2-windows-portable.zip`.
- **Source-run users**: download `DiceFrame-v2.3.2-windows.zip`.
- `.sha256` files are update checksums. Keep the previous version or a data backup to make rollback easy.
