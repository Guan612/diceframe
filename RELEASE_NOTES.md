# DiceFrame v2.4.2-beta.1

> 这是预览版本，主要验证世界书可见性改进、内置世界书升级迁移与相关兼容性。重要数据请提前备份。

## 中文

### 本次更新

- **世界书视角检查器**：世界书页新增 GM / 全队 / 各角色视角的可见性检查器，可按视角筛选条目并查看受众构成；检查器的展开状态会跨会话记忆，窄屏抽屉默认收起。
- **AI 生成世界书可见性**：AI 生成世界书条目时按内容性质分配 GM 秘密 / 全队公开 / 指定角色可见，并受提示词安全契约约束，AI 输出不直接绕过权威可见性规则。
- **可见性编辑兼容**：世界书编辑器提供 GM 秘密 / 全队公开 / 指定角色三档控制；兼容历史数据中的 `PUBLIC`、`公开` 等大小写与别名写法以及 `"Alice,Bob"` 逗号分隔字符串，公开标记不再被误判后在保存时静默变成 GM 秘密。
- **内置世界书内容重审计**：混合"公开常识 + GM 调查线索"的内置条目被拆分为公开条目与秘密条目；公开常识对所有玩家生效，秘密线索保持 GM-only。
- **老安装升级迁移**：老存档首次启动时会自动把仍与旧官方默认完全一致的条目升级到重审计后的公开/秘密状态；迁移目标在发布时冻结、逐字段检测用户修改、幂等执行——用户编辑过的条目绝不会被系统模板覆盖，无法安全判定的场景一律保留原状。
- **界面细节**：原生复选框与单选框尺寸、设置页数字对齐、资料库卡片操作按钮布局、移动端全宽导航、导航分组标题精简、助手问候气泡等一系列界面改进。
- **测试与工程治理**：精简测试套件；新增工程规范（`docs/ENGINEERING_RULES.md`）、ADR 指南（`docs/adr/`）与风险导向的 PR 模板，明确"规范约束风险和契约，不冻结当前实现"。

### 升级提示

- 这是预览版本；升级前请备份完整的 `data/` 文件夹。
- 老存档首次启动会执行一次内置世界书升级迁移：只有仍与旧官方默认逐字段一致的条目才会升级；用户修改过的条目保留原样。
- Docker Update 当前支持 `linux-amd64`。

### 下载与校验

- Windows 便携版：`DiceFrame-v2.4.2-beta.1-windows-portable.zip`
- Windows 源码包：`DiceFrame-v2.4.2-beta.1-windows.zip`
- Docker 托管更新：`DiceFrame-v2.4.2-beta.1-docker-update-linux-amd64.zip`
- 手动下载时，请使用 Release 中的 `SHA256SUMS` 统一校验。

## English

### What's changed

- **Lorebook perspective inspector**: The lorebook page gains a visibility inspector for the GM / party / each character perspective, with per-perspective entry filtering and audience breakdown. The inspector remembers its collapsed state across sessions and stays collapsed by default on narrow screens.
- **AI-generated lore visibility**: AI-generated lorebook entries receive GM-secret / party-wide / named-character visibility based on content nature, bounded by a prompt-safety contract so AI output never bypasses authoritative visibility rules.
- **Visibility editing compatibility**: The lorebook editor offers three explicit visibility modes and tolerates historical shapes such as `PUBLIC`-style casing/aliases and comma-separated `"Alice,Bob"` strings. Public markers are no longer misclassified and silently stripped to GM-secret on save.
- **Built-in lore re-audit**: Built-in entries that mixed public common knowledge with GM-only clues are split into a public entry and a secret entry. Common knowledge is now party-visible while investigative clues stay GM-only.
- **Upgrade migration for existing installs**: On first startup, existing databases migrate old official entries to the re-audited public/secret state only when every field still matches the pre-regrade official default. The migration target is frozen at publish time, user edits are detected field-by-field, and execution is idempotent — user-edited entries are never overwritten, and anything that cannot be judged safely is left untouched.
- **UI polish**: Native checkbox/radio sizing, settings number alignment, library card action layout, full-width mobile navigation, simplified navigation group titles, assistant greeting bubble, and more.
- **Tests and engineering governance**: The test suite is slimmed; engineering rules (`docs/ENGINEERING_RULES.md`), ADR guidance (`docs/adr/`), and a risk-oriented PR template are added, making explicit that governance constrains risk and contracts rather than freezing the current architecture.

### Upgrade notes

- This is a preview release; back up the complete `data/` directory before upgrading.
- Existing databases run a one-time built-in lore upgrade migration on first startup: only entries still matching the old official default field-for-field are upgraded; user-edited entries are preserved as-is.
- Docker Update currently supports `linux-amd64`.

### Downloads and verification

- Windows portable: `DiceFrame-v2.4.2-beta.1-windows-portable.zip`
- Windows source: `DiceFrame-v2.4.2-beta.1-windows.zip`
- Managed Docker update: `DiceFrame-v2.4.2-beta.1-docker-update-linux-amd64.zip`
- For manual downloads, verify all archives with the `SHA256SUMS` file attached to the Release.
