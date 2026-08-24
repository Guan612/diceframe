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

Rule core 保留 `dice_system`、`damage_dice`、`ac_base`、`dex_cap`、`attribute_points`、`proficiency`、`combat_model`、伤害/死亡机制以及 permissions、capabilities、scripts。Typed locale 只能提供显示和语言字段；嵌套 unknown/mechanics 字段必须拒绝。

## World Locale

World core 拥有 `world_id`、`default_rule`、`recommended_rules`、`suggested_difficulty` 以及 starter lorebook 的 entry set/order、ID、type、tier、`unreliable`、`sync_on_enter`、`triggers_recursive`、`visible_to`、`match_mode`、`sticky`、`cooldown`、`delay`、`order`、`probability`、`group`、`group_weight`、`connected_to` 等确定性字段。

World locale 只能修改 `world_name`、`description`、`world_setting`、`starter_scene`，以及按 canonical lore entry ID 修改 `name`、`keywords`、`content`。World Locale cannot replace `starter_lorebook` entries. Language changes cannot add, remove, or rename canonical lore identities。

例如 core ID 为 `npc_innkeeper`，中文可以是 `npc_innkeeper.name = 老汤姆`，英文可以是 `npc_innkeeper.name = Old Tom`；identity 永远是 `npc_innkeeper`。

## Plugin Content V2

Manifest 当前支持：`schema_version = 1`、`content_schema_version = 1 or 2`、`locale_schema_version = 1`，以及 package locale fallback 的 `default_locale`。Locale fallback 为 exact requested locale -> base locale -> package/default locale -> base(default locale) -> canonical/core display fallback。

`ResourceRef` 示例：`core:item:longsword`、`plugin:my-pack:item:moon_blade`。普通 V2 item/class/spell/npc/character_template 可以通过 namespace 共存。Rule/World 仍主要使用 plain `rule_id` / `world_id`，因此不同 V2 plugin 的重复 Rule/World ID 必须明确拒绝，不能 first-wins 或 last-wins。

## Migration 与 Compatibility

`src/migrations/` 负责 persisted schema upgrade；`src/compat/` 负责 old external/runtime shape 到当前 canonical model 的兼容。V1 包通过适配器读取，不能把兼容分支散回正常业务逻辑。

## Frontend 与规则边界

Backend materializes V2 locale，frontend 只渲染返回字段，不重新实现 Content V2 locale architecture。D&D 如何使用 d20 不等于修改 generic d20 本身；D&D 专属行为必须留在 D&D 边界内。
