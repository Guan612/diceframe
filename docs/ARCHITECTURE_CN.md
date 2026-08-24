# DiceFrame 架构事实来源

本文描述当前实现，不是路线图。代码依赖方向为 `routes -> WebAPI -> services -> 核心`；核心层不得导入 `src.webui`，WebAPI 是委托层，跨 service 调用经由 API 委托。

## Content V2

所有输入先经过兼容边界，再进入当前 canonical model：

```text
Legacy / V1 Rule / Plugin / Save / World / Character
                    ↓
              Compatibility
                    ↓
          Canonical Current Model
                    ↓
            Runtime Mechanics
                    ↓
             Typed Locale
                    ↓
                   UI
```

Canonical identity 是稳定引用键，例如 `fighter`、`longsword`、`chain_mail`、`athletics`、`str`、`npc_innkeeper`。`战士 / Fighter`、`长剑 / Longsword / ロングソード`、`老汤姆 / Old Tom` 只是 display text。切换语言不得改变 ID。

正常 V2 runtime 的 mechanics authority 是 canonical rule/content。`ARMOR_LITE`、`WEAPON_DAMAGE`、`WEAPON_DAMAGE_DICE` 等旧表只用于旧存档、V1 或 legacy fallback。

## Rule Locale

Rule core 保留 `dice_system`、`damage_dice`、`ac_base`、`dex_cap`、`attribute_points`、`proficiency`、`combat_model`、`skill_pools`、`item_categories`、伤害/死亡机制以及 permissions、capabilities、scripts。职业技能池使用 class/skill canonical ID；typed locale 只能翻译这些 ID 的显示名，不能替换技能池或物品分类。嵌套 unknown/mechanics 字段必须拒绝。

## World Locale

World core 拥有 `world_id`、`default_rule`、`recommended_rules`、`suggested_difficulty` 以及 starter lorebook 的 entry set/order、ID、type、tier、`unreliable`、`sync_on_enter`、`triggers_recursive`、`visible_to`、`match_mode`、`sticky`、`cooldown`、`delay`、`order`、`probability`、`group`、`group_weight`、`connected_to` 等确定性字段。

World locale 只能修改 `world_name`、`description`、`world_setting`、`starter_scene`，以及按 canonical lore entry ID 修改 `name`、`keywords`、`content`。World Locale cannot replace `starter_lorebook` entries. Language changes cannot add, remove, or rename canonical lore identities。

例如 core ID 为 `npc_innkeeper`，中文可以是 `npc_innkeeper.name = 老汤姆`，英文可以是 `npc_innkeeper.name = Old Tom`；identity 永远是 `npc_innkeeper`。

世界书数据库保存 canonical/core 条目；关键词匹配、prompt 和谜题初始化按每局 `GameInstance.language` 构造只读本地化视图，不把译文写回共享数据库。

## Plugin Content V2

Manifest 当前支持：`schema_version = 1`、`content_schema_version = 1 or 2`、`locale_schema_version = 1`，以及 package locale fallback 的 `default_locale`。Locale fallback 为 exact requested locale -> base locale -> package/default locale -> base(default locale) -> canonical/core display fallback。

`ResourceRef` 示例：`core:item:longsword`、`plugin:my-pack:item:moon_blade`。普通 V2 item/class/spell/npc/character_template 可以通过 namespace 共存。Rule/World 仍主要使用 plain `rule_id` / `world_id`，因此不同 V2 plugin 的重复 Rule/World ID 必须明确拒绝，不能 first-wins 或 last-wins。

V2 资源 ID 必须已经是 canonical 形式；注册器不会替插件把大小写、空格或非 ASCII ID 悄悄归一化。V2 locale 或内容校验失败时，目录 API 返回 `CONTENT_VALIDATION_FAILED`，不得省略损坏资源或回退到未本地化内容。应用内内容包导出器始终生成 Content V2 core + typed locale 布局；V1 全文副本只在导入适配器中支持。

## Migration 与 Compatibility

`src/migrations/` 负责 persisted schema upgrade；`src/compat/` 负责 old external/runtime shape 到当前 canonical model 的兼容。V1 包通过适配器读取，不能把兼容分支散回正常业务逻辑。

## Frontend 与规则边界

Backend materializes V2 locale，frontend 只渲染返回字段，不重新实现 Content V2 locale architecture。D&D 如何使用 d20 不等于修改 generic d20 本身；D&D 专属行为必须留在 D&D 边界内。

## Ruleset Runtime

`src/rulesets/` 是版本化规则运行时边界。规则模板缺少 `runtime` 时显式回退到 `core:legacy`，继续使用现有 RuleSystem、RoundProcessor、CombatResolver 和 ProgressionResolver。新运行时必须由 canonical `runtime.id` 绑定，不能根据 `rule_id`、翻译名或 mechanics 字符串模糊推断。未知或版本不兼容的 runtime 必须拒绝。

Ruleset runtime 可导入通用 engine 原语；generic engine、generic d20、memory、lorebook 不得反向导入任何具体规则运行时。WebAPI 和前端只通过 `ruleset_runtime` capabilities 了解体验能力。

## Ruleset Bundle v1

`templates/rulesets/<directory_id>/` 是第一方专业规则的离线内容快照，不是 Plugin Content V2 的替代。Bundle manifest 绑定 `bundle_id`、`runtime_id`、规则/内容版本、locale 与归属文件。Canonical entity 必须具有稳定 `kind:id`、`source_ref` 和 `automation_level`。

Bundle locale 只能物化白名单展示字段。效果使用白名单 DSL；任意代码执行键、未知效果原语、重复 ID、无效内部引用、越界归属路径或 locale mechanics override 都会使整个 bundle 加载失败。详细格式见 `docs/rulesets/dnd2024/CONTENT_BUNDLE_CN.md`。

## D&D 2024 权威游戏状态

`core:dnd2024` 的战斗、Session 0、战役记录和教学冒险共享 `GameInstance.ruleset_state.version` 与 EventBatch ledger。战斗事件只由战斗 reducer 应用，战役事件只由 campaign reducer 应用；runtime composition root 按显式 `intent_type` 分派，generic engine 不导入 D&D 实现。

专业角色的机械权威是 `ruleset_character`。创建、共享卡库导入/编辑、加入游戏、游戏内资料编辑、升级和休息均经由 `character_lifecycle` capability；legacy 顶层角色字段只是兼容投影。资料编辑不得覆盖属性、HP、AC、成长历史、runtime/content/state 版本等机械字段，机械更新必须从 canonical 选择与历史重新验证或回放。

Session 0 的每次修订都会清空旧成员确认，只有全部当前玩家接受后 GM 才能锁定。任务、线索、事实、重要物品和关系先保存为 pending proposal，再由 GM 以独立 Intent 确认或拒绝。章节摘要是已确认事件的确定性投影，并在存档成功后写入长期记忆；记忆投影失败不得回滚或伪装已经持久化的权威状态。

专业规则通过 `narrative_adventure` capability 接受自然语言冒险行动。Session 0 和教学状态决定输入是否可用；动作先完成模型预检，失败不会写入记录。LLM 只接收权威状态的只读视图并叙述行动或已结算事件，不能直接创建战役事实、扣减资源或推进教学步骤。

前端仅按 capability 动态加载 D&D 专业规则游玩区。游玩区使用“1 从这里开始 / 2 遇敌时战斗 / 3 回看故事（可选）”三页签，并在首屏说明当前目标和下一步；任一时刻只挂载当前面板并在页面隐藏时暂停轮询。内容在有界区域内部滚动，不改变旧规则的布局或创建路径。直接联机桥接对玩家 Intent 使用字段白名单。
