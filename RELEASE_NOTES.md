# DiceFrame v2.4.0-beta.1

## 中文

DiceFrame 2.4.0-beta.1 是高级 DND5E 自动化体验与 Docker 托管更新的首个公开预览。该版本改动范围较大，请先备份现有 `data/`，并在重要战役的副本上验证后再升级。

### DND5E 高级规则

- **统一游玩流程**：高级规则继续使用公共时间线、行动输入框、队伍状态、世界书和 GM 控制台；DND5E 工具只承载冒险/战役与权威战斗，不再建立第二套消息流。
- **AI GM 自动化**：新增受约束的导演规划、剧情遭遇唤醒、多人行动收集和敌方回合自动结算。战斗资源、先攻、伤害、休息与升级仍由服务端权威状态机处理。
- **多人战斗体验**：玩家准备状态、当前行动者、战斗事件和公共行动历史实时同步；玩家只能操作自己的角色，GM 保留遭遇与战役裁定权。
- **角色与成长**：高级角色中心、法术资源、休息和逐级升级流程统一到 canonical 角色生命周期，并支持里程碑或 XP 升级资格。
- **叙事一致性**：游戏级第一/第三人称视角同时作用于通用叙事，角色、NPC 与公共战斗历史使用更清晰的身份区分。

### 世界书与冒险包

- **职责分离**：世界书继续决定世界背景和 lore；可选冒险包提供章节、场景、NPC、地图引用和遭遇结构，两者组合但不互相覆盖。
- **冒险包管理**：新增可视化新建、复制、编辑、校验、导入、导出、删除和 AI 草稿流程。已被存档绑定的包保持只读，避免重开时内容漂移。
- **稳定重开**：存档精确绑定冒险 identity、版本和内容摘要；旧的未发布绑定通过明确兼容边界迁移，未知或已变化内容会直接报告错误。

### Docker 托管更新

- **容器内普通更新**：新 Docker 基线镜像使用稳定 launcher 管理当前/上一应用版本，候选通过健康检查和观察期后提交，失败自动回滚。
- **统一发布产物**：GitHub Release、GHCR 和 Docker Hub 镜像消费同一份 Linux AMD64 Docker Update ZIP，并强制校验版本、平台、CPython ABI、runtime API、SHA-256 和安全解包边界。
- **安全边界**：不挂载 Docker socket，不要求 privileged，不从应用内控制 Docker daemon；不可证明数据可回滚的更新包会被拒绝。

### 预览提示

- 旧 Docker 镜像不具备 launcher，Docker 用户需要手动拉取并重建一次 `v2.4.0-beta.1` 基线镜像；之后的普通兼容版本才能在设置页内更新。
- Docker Update 首期仅支持 `linux-amd64`。Python ABI、系统库或 launcher 协议变化仍需更新基础镜像。
- 高级 DND5E 与冒险包仍为测试版；传统规则、CoC、赛博朋克和 generic d20 不会自动启用 DND 专属机制。
- 玩家直连仍受 NAT、防火墙和房主在线状态影响。

### 下载

- Windows 便携版：`DiceFrame-v2.4.0-beta.1-windows-portable.zip`
- Windows 源码包：`DiceFrame-v2.4.0-beta.1-windows.zip`
- Docker 托管更新：`DiceFrame-v2.4.0-beta.1-docker-update-linux-amd64.zip`
- 所有手工附件使用统一 `SHA256SUMS` 校验。

## English

DiceFrame 2.4.0-beta.1 is the first public preview of the advanced DND5E automation experience and managed Docker updates. This is a broad release: back up `data/` and validate a copy of any important campaign before upgrading.

### Advanced DND5E rules

- **One play flow**: advanced rules keep the shared timeline, action composer, party state, lorebook, and GM console. DND5E tools contain campaign and authoritative combat controls without creating a second message stream.
- **AI GM automation**: constrained director planning, narrative encounter activation, multiplayer action collection, and automated enemy turns are now available. Initiative, damage, rests, advancement, and combat resources remain server-authoritative.
- **Multiplayer combat**: readiness, active turn, combat events, and public action history synchronize in real time. Players control only their own characters while the GM retains encounter and campaign authority.
- **Characters and progression**: the advanced character center, spells, rests, and level-by-level advancement use the canonical character lifecycle, with milestone or XP-based advancement eligibility.
- **Narrative consistency**: game-level first- or third-person perspective applies to the shared narrative, with clearer visual identity for players, NPCs, and combat history.

### Lorebooks and adventures

- **Separate responsibilities**: lorebooks define world context and lore; optional adventure bundles provide chapters, scenes, NPCs, map references, and encounter structure without overwriting the selected world.
- **Adventure management**: create, copy, edit, validate, import, export, delete, and AI-draft workflows are available. Bundles referenced by saves remain immutable.
- **Deterministic resume**: saves pin adventure identity, version, and content digest. Known unreleased bindings migrate through an explicit compatibility boundary; missing or changed content fails with a structured error.

### Managed Docker updates

- **In-container application updates**: the new Docker baseline uses a stable launcher to manage current and previous application payloads. Candidates commit only after health checks and probation, with automatic rollback on failure.
- **One release artifact**: GitHub Release, GHCR, and Docker Hub consume the same Linux AMD64 Docker Update ZIP. Version, platform, CPython ABI, runtime API, SHA-256, and extraction safety are fail-closed.
- **Security boundary**: DiceFrame does not mount the Docker socket, require privileged mode, or control the Docker daemon. Packages without an explicit data-rollback guarantee are rejected.

### Preview notes

- Existing Docker images do not contain the launcher. Docker users must manually pull and recreate the `v2.4.0-beta.1` baseline once; later compatible application releases can then update from Settings.
- Docker Update currently supports `linux-amd64` only. Python ABI, system-library, or launcher-protocol changes still require a base-image update.
- Advanced DND5E and adventure bundles remain beta features. Traditional rules, CoC, cyberpunk, and generic d20 do not inherit DND-specific mechanics.
- Direct player connections remain subject to NAT, firewall, and host-availability limits.

### Downloads

- Windows portable: `DiceFrame-v2.4.0-beta.1-windows-portable.zip`
- Windows source: `DiceFrame-v2.4.0-beta.1-windows.zip`
- Managed Docker update: `DiceFrame-v2.4.0-beta.1-docker-update-linux-amd64.zip`
- Verify all manually produced assets with `SHA256SUMS`.
